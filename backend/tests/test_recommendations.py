import unittest

from app.main import SCHEMES, RAG_CHUNKS, check, extract, recommendations
from app.recommendations import metadata_for
from app.taxonomy import detect_intent


def run_query(text):
    profile = extract(text)
    return profile, recommendations(profile, text)


class RecommendationRegressionTests(unittest.TestCase):
    def ids(self, result):
        return {scheme["id"] for scheme in result["recommendations"]}

    def targets(self, result):
        return {target for scheme in result["recommendations"]
                for target in scheme["recommendation_metadata"]["target_groups"]}

    def test_student_bug_case_stays_in_education(self):
        text = "I am a 22-year-old student from Lucknow looking for financial help for my studies."
        profile, result = run_query(text)
        self.assertEqual(detect_intent(text, profile)["primary_category"], "EDUCATION")
        self.assertTrue(profile["student_status"])
        self.assertNotIn("farmer_status", profile)  # Unmentioned traits stay unknown.
        self.assertNotIn("widow_status", profile)
        self.assertTrue(self.ids(result))
        self.assertTrue(all(s["recommendation_metadata"]["category_key"] == "EDUCATION" for s in result["recommendations"]))
        self.assertFalse(self.targets(result) & {"FARMER", "WIDOW", "SENIOR_CITIZEN"})

    def test_farmer_does_not_receive_student_or_widow_schemes(self):
        profile, result = run_query("I am a farmer from Uttar Pradesh.")
        self.assertTrue(profile["farmer_status"])
        self.assertTrue(self.targets(result) <= {"FARMER"})
        self.assertFalse(self.targets(result) & {"STUDENT", "WIDOW"})

    def test_senior_citizen_does_not_receive_student_schemes(self):
        _, result = run_query("I am a 68-year-old retired person.")
        self.assertIn("SENIOR_CITIZEN", result["roles"])
        self.assertFalse(self.targets(result) & {"STUDENT"})

    def test_senior_age_rule_numeric_strings_are_safe(self):
        for value in ("60", 60, 60.0, ["60", "100"], [60, 100], [60.0, 100.0]):
            with self.subTest(value=value):
                metadata = metadata_for({
                    "id": "senior-string-age",
                    "category": "General Welfare",
                    "rules": [{"field": "age", "operator": ">=", "value": value}],
                })
                self.assertIn("SENIOR_CITIZEN", metadata["target_groups"])

        categorical = metadata_for({
            "id": "categorical-age",
            "category": "General Welfare",
            "rules": [{"field": "age", "operator": ">=", "value": "elderly"}],
        })
        self.assertNotIn("SENIOR_CITIZEN", categorical["target_groups"])

    def test_widow_does_not_receive_farmer_only_schemes(self):
        _, result = run_query("I am a widow with two children.")
        self.assertIn("WIDOW", result["roles"])
        self.assertFalse(self.targets(result) & {"FARMER"})

    def test_multiple_roles_keep_both_relevant_categories(self):
        profile, result = run_query("I am a student and also work on my family's farm.")
        self.assertTrue(profile["student_status"])
        self.assertTrue(profile["farmer_status"])
        self.assertTrue(self.targets(result) & {"STUDENT"})
        self.assertTrue(self.targets(result) & {"FARMER"})

    def test_not_a_farmer_is_a_hard_exclusion(self):
        profile, result = run_query("I am a student, not a farmer.")
        self.assertFalse(profile["farmer_status"])
        self.assertFalse(self.targets(result) & {"FARMER"})

    def test_missing_required_disability_is_unknown_not_false(self):
        scheme = next(s for s in SCHEMES if any(r["field"] in {"disability", "disability_status"} for r in s["rules"]))
        status = check(scheme, {"student_status": True})
        disability_check = next(c for c in status["checks"] if c["field"] in {"disability", "disability_status"})
        self.assertEqual(disability_check["status"], "UNKNOWN")

    def test_empty_rag_index_keeps_metadata_pipeline_operational(self):
        profile = {"student_status": True, "state": "Uttar Pradesh"}
        result = __import__("app.recommendations", fromlist=["rank_recommendations"]).rank_recommendations(
            SCHEMES, profile, "college scholarship", [], check_fn=check)
        self.assertFalse(result["rag_available"])
        self.assertTrue(result["recommendations"])
        self.assertTrue(all(s["recommendation_metadata"]["category_key"] == "EDUCATION" for s in result["recommendations"]))


if __name__ == "__main__":
    unittest.main()
