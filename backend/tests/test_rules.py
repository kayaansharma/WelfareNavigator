import unittest
from app.main import check, evaluate, DEMO_USERS, SCHEMES, DEMO_USER_DOCUMENTS, demo_user_record
class RulesTests(unittest.TestCase):
    def rule(self, field="age", operator="<=", value=30): return {"field":field,"operator":operator,"value":value,"description":"test"}
    def test_age_match_and_fail(self):
        self.assertEqual(evaluate(self.rule(),{"age":24}),"MATCHED")
        self.assertEqual(evaluate(self.rule(),{"age":45}),"FAILED")
    def test_missing_is_unknown(self): self.assertEqual(evaluate(self.rule("annual_income","<=",250000),{}),"UNKNOWN")
    def test_state_match_and_fail(self):
        r=self.rule("state","IN",["Uttar Pradesh"])
        self.assertEqual(evaluate(r,{"state":"Uttar Pradesh"}),"MATCHED")
        self.assertEqual(evaluate(r,{"state":"Bihar"}),"FAILED")
    def test_and_or(self):
        self.assertEqual(evaluate(self.rule("unused","AND",{"age":24,"student_status":True}),{"age":24,"student_status":True}),"MATCHED")
        self.assertEqual(evaluate(self.rule("unused","OR",{"age":24,"student_status":True}),{"age":19,"student_status":True}),"MATCHED")
    def test_overall_scheme_status(self):
        scheme={"id":"x","rules":[self.rule("age","<=",30),self.rule("income","<=",100)]}
        self.assertEqual(check(scheme,{"age":24})["status"],"NEEDS_MORE_INFORMATION")
        self.assertEqual(check(scheme,{"age":24,"income":50})["status"],"POTENTIAL_MATCH")
        self.assertEqual(check(scheme,{"age":40,"income":50})["status"],"APPEARS_UNLIKELY")
    def test_multiple_unknowns(self):
        self.assertEqual(evaluate(self.rule("x","IN",["a"]),{}),"UNKNOWN")
        self.assertEqual(evaluate(self.rule("y",">=",1),{}),"UNKNOWN")
    def test_csv_seed_is_loaded(self):
        self.assertEqual(len(SCHEMES),40)
        self.assertEqual(len(DEMO_USERS),40)
        self.assertEqual(len(DEMO_USER_DOCUMENTS),110)
    def test_csv_between_and_alias(self):
        rule=self.rule("age","BETWEEN",[18,40])
        self.assertEqual(evaluate(rule,{"age":24}),"MATCHED")
        self.assertEqual(evaluate(rule,{"age":60}),"FAILED")
        income=self.rule("annual_family_income","<=",450000)
        self.assertEqual(evaluate(income,{"annual_income":180000}),"MATCHED")
    def test_demo_profile_includes_sample_documents(self):
        user=demo_user_record("U001")
        self.assertEqual(user["profile"]["annual_income"],180000)
        self.assertTrue(user["profile"]["is_student"])
        self.assertEqual(len(user["documents"]),3)
if __name__=="__main__": unittest.main()
