import unittest

from app.main import PROFILE, ChatRequest, run_agent_query, extract
from app.taxonomy import detect_intent, detect_language


class AgentPipelineTests(unittest.TestCase):
    def setUp(self):
        self.saved = dict(PROFILE)
        PROFILE.clear()
        PROFILE.update({key: None for key in self.saved if key not in {"_statuses", "existing_benefits", "language"}})
        PROFILE.update(_statuses={}, existing_benefits=[], language="English")

    def tearDown(self):
        PROFILE.clear()
        PROFILE.update(self.saved)

    def test_language_detection_handles_three_modes(self):
        self.assertEqual(detect_language("I need a scholarship"), "English")
        self.assertEqual(detect_language("मुझे छात्रवृत्ति चाहिए"), "Hindi")
        self.assertEqual(detect_language("Main student hoon, mujhe scholarship chahiye"), "Hinglish")

    def test_student_hinglish_extracts_age_city_income_and_intent(self):
        query = "Main 22 saal ka student hoon aur Lucknow mein rehta hoon. Meri family income 1.5 lakh hai. Mujhe padhai ke liye scholarship chahiye."
        fields = extract(query)
        intent = detect_intent(query, fields)
        self.assertEqual(fields["age"], 22)
        self.assertTrue(fields["student_status"])
        self.assertEqual(fields["city"], "Lucknow")
        self.assertEqual(fields["annual_income"], 150000)
        self.assertEqual(intent["primary_category"], "EDUCATION")
        self.assertIn("FINANCIAL_ASSISTANCE", intent["secondary_categories"])

    def test_hinglish_farmer_widow_and_senior_intents(self):
        farmer = extract("Main ek farmer hoon aur fasal ke liye financial support chahiye.")
        self.assertTrue(farmer["farmer_status"])
        self.assertEqual(detect_intent("Main ek farmer hoon aur fasal ke liye financial support chahiye.", farmer)["primary_category"], "AGRICULTURE")
        widow_query = "meri maa widow hain aur unhe financial help chahiye"
        widow = extract(widow_query)
        self.assertTrue(widow["widow_status"])
        self.assertEqual(widow["beneficiary_relationship"], "mother")
        widow_intent = detect_intent(widow_query, widow)
        self.assertIn("SOCIAL_WELFARE", [widow_intent["primary_category"], *widow_intent["secondary_categories"]])
        self.assertIn("WOMEN_CHILD", widow_intent["secondary_categories"])
        senior = extract("I am 68 years old and need pension information.")
        self.assertTrue(senior["senior_citizen_status"])
        self.assertIn("SENIOR_CITIZEN", [detect_intent("pension information", senior)["primary_category"]])

    def test_agent_query_is_single_orchestration_and_returns_grounded_education_results(self):
        response = run_agent_query(ChatRequest(message="Main 22 saal ka student hoon, Lucknow mein rehta hoon aur mere family ki income 1.5 lakh hai. Mujhe padhai ke liye government scholarship ya financial help chahiye.", language="Hinglish"))
        self.assertEqual(response["language"], "Hinglish")
        self.assertEqual(response["profile"]["annual_income"], 150000)
        self.assertEqual(response["profile"]["city"], "Lucknow")
        self.assertEqual(response["intent"]["primary_category"], "EDUCATION")
        self.assertIn("FINANCIAL_ASSISTANCE", response["intent"]["secondary_categories"])
        self.assertTrue(response["recommendations"])
        self.assertTrue(all(s["recommendation_metadata"]["category_key"] == "EDUCATION" for s in response["recommendations"]))
        self.assertTrue(all(s["source"].get("source_url") for s in response["recommendations"]))

    def test_follow_up_keeps_missing_values_unknown(self):
        response = run_agent_query(ChatRequest(message="I am a student and need financial help.", language="English"))
        self.assertIsNone(response["profile"]["age"])
        self.assertIsNone(response["profile"]["annual_income"])
        self.assertIsNone(response["profile"]["disability_status"])
        self.assertTrue(response["follow_up_question"])


if __name__ == "__main__":
    unittest.main()
