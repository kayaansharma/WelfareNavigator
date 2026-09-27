import unittest
from types import SimpleNamespace
from fastapi.testclient import TestClient

from app import database
from app import main


class FakeQuery:
    def __init__(self, client, table):
        self.client, self.table_name = client, table
        self.start, self.end, self.limit_count = 0, None, None
        self.filters, self.operation, self.payload = [], "select", None

    def select(self, _columns): return self
    def range(self, start, end): self.start, self.end = start, end; return self
    def limit(self, count): self.limit_count = count; return self
    def eq(self, field, value): self.filters.append((field, value)); return self
    def update(self, values): self.operation, self.payload = "update", values; return self
    def insert(self, values): self.operation, self.payload = "insert", values; return self

    def execute(self):
        rows = self.client.tables.setdefault(self.table_name, [])
        if self.operation == "insert":
            row = {"id": f"new-{len(rows)+1}", **self.payload}
            rows.append(row)
            return SimpleNamespace(data=[row])
        if self.operation == "update":
            matching = [r for r in rows if all(str(r.get(k)) == str(v) for k, v in self.filters)]
            for row in matching: row.update(self.payload)
            return SimpleNamespace(data=matching)
        matching = [r for r in rows if all(str(r.get(k)) == str(v) for k, v in self.filters)]
        if self.limit_count is not None: matching = matching[:self.limit_count]
        if self.end is not None: matching = matching[self.start:self.end+1]
        return SimpleNamespace(data=matching)


class FakeSupabase:
    def __init__(self, tables): self.tables = tables
    def table(self, name): return FakeQuery(self, name)


def demo_tables():
    profiles = [{"user_id": f"uuid-{i:03}", "attributes": {"user_id": f"U{i:03}", "name": f"Demo {i}", "age": 22 if i == 1 else 30, "annual_family_income": 180000 if i == 1 else 300000, "is_student": i == 1}, "field_status": {}, "language": "English"} for i in range(1, 41)]
    return {
        "schemes": [{"id": f"S{i:02}", "name": f"Scheme {i}", "description": "Support", "government": "Central", "state": "All India", "category": "Education", "benefits": "Support", "eligibility_summary": "Demo", "application_process": "Apply", "application_url": "https://example.org", "source_url": "https://example.org", "source_name": "Example", "last_verified": "2026-01-01", "active": True, "synthetic": False} for i in range(40)],
        "eligibility_rules": [{"scheme_id": f"S{i%40:02}", "field": "age", "operator": "less_than_or_equal", "value": 60+i, "description": "Age limit", "required": True, "group_operator": None} for i in range(128)],
        "scheme_documents": [{"id": i, "scheme_id": f"S{i%40:02}", "document_type": f"Document {i}", "required": i%2 == 0} for i in range(92)],
        "scheme_categories": [{"category_id": f"C{i:02}", "category_name": f"Category {i}", "description": "Demo category"} for i in range(15)],
        "profiles": profiles,
        "user_documents": [{"id": f"doc-{i:03}", "user_id": f"uuid-{1+(i%40):03}", "filename": f"File {i}.pdf", "private_storage_key": "secret-path", "content_type": "application/pdf", "status": "UPLOADED", "created_at": "2026-01-01"} for i in range(110)],
    }


class DatabaseIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = FakeSupabase(demo_tables())
        self.old_client, self.old_initialized = database._client, database._client_initialized
        self.old_source = main.DATABASE_SOURCE
        self.old_profile, self.old_documents, self.old_active_user = dict(main.PROFILE), list(main.DOCUMENTS), main.ACTIVE_SUPABASE_USER_ID
        database.set_client_for_tests(self.client)

    def tearDown(self):
        database.set_client_for_tests(self.old_client, self.old_initialized)
        main.DATABASE_SOURCE = self.old_source
        main.PROFILE.clear(); main.PROFILE.update(self.old_profile)
        main.DOCUMENTS = self.old_documents
        main.ACTIVE_SUPABASE_USER_ID = self.old_active_user

    def test_supabase_catalog_has_expected_row_counts_and_maps_documents(self):
        schemes, users, user_docs, categories = database.load_catalog(self.client)
        self.assertEqual((len(schemes), sum(len(s["rules"]) for s in schemes), sum(len(s["documents"]) for s in schemes), len(categories)), (40, 128, 92, 15))
        self.assertEqual(schemes[0]["documents"][0]["name"], "Document 0")
        self.assertEqual(schemes[0]["rules"][0]["operator"], "<=")
        self.assertEqual(len(users), 40)
        self.assertEqual(len(user_docs), 110)

    def test_supabase_rules_normalize_values_and_dedupe_only_exact_semantic_duplicates(self):
        tables = demo_tables()
        tables["schemes"][36]["id"] = "S036"
        duplicate_yes = {"scheme_id": "S036", "field": "is_student", "operator": "equals", "value": "Yes", "required": True, "group_operator": "AND", "description": "Student"}
        tables["eligibility_rules"] = [
            duplicate_yes,
            {**duplicate_yes, "operator": "==", "value": True, "description": "Duplicate wording"},
            {**duplicate_yes, "required": False},
            {**duplicate_yes, "group_operator": "OR"},
            {"scheme_id": "S036", "field": "age", "operator": ">=", "value": "60", "required": True, "group_operator": None},
            {"scheme_id": "S036", "field": "age", "operator": "BETWEEN", "value": ["18", "60"], "required": True, "group_operator": None},
            {"scheme_id": "S036", "field": "social_category", "operator": "IN", "value": ["OBC", "SC"], "required": True, "group_operator": None},
            {"scheme_id": "S036", "field": "state", "operator": "equals", "value": "true", "required": True, "group_operator": None},
        ]
        client = FakeSupabase(tables)
        schemes, _, _, _ = database.load_catalog(client)
        rules = next(scheme["rules"] for scheme in schemes if scheme["id"] == "S036")

        student_rules = [rule for rule in rules if rule["field"] == "is_student"]
        self.assertEqual(len(student_rules), 3)
        self.assertEqual(student_rules[0]["operator"], "==")
        self.assertIs(student_rules[0]["value"], True)
        self.assertEqual(main.evaluate(student_rules[0], {"is_student": True}), "MATCHED")
        self.assertEqual(next(rule["value"] for rule in rules if rule["field"] == "age" and rule["operator"] == ">="), 60)
        self.assertEqual(next(rule["value"] for rule in rules if rule["operator"] == "BETWEEN"), [18, 60])
        self.assertEqual(next(rule["value"] for rule in rules if rule["field"] == "social_category"), ["OBC", "SC"])
        self.assertEqual(next(rule["value"] for rule in rules if rule["field"] == "state"), "true")

    def test_demo_u001_profile_and_documents_resolve_through_profile_attributes(self):
        main.DATABASE_SOURCE = "supabase"
        record = main.demo_user_record("U001")
        self.assertEqual(record["profile"]["annual_income"], 180000)
        self.assertTrue(record["profile"]["student_status"])
        self.assertEqual(record["_supabase_user_id"], "uuid-001")
        self.assertTrue(record["documents"])
        self.assertNotIn("private_storage_key", record["documents"][0])

    def test_load_demo_user_keeps_uuid_internal(self):
        main.DATABASE_SOURCE = "supabase"
        loaded = main.load_demo_user("U001")
        self.assertEqual(loaded["profile"]["annual_income"], 180000)
        self.assertEqual(main.ACTIVE_SUPABASE_USER_ID, "uuid-001")
        self.assertNotIn("_supabase_user_id", loaded)

    def test_demo_user_endpoint_does_not_return_supabase_uuid(self):
        main.DATABASE_SOURCE = "supabase"
        record = main.get_demo_user("U001")
        self.assertEqual(record["user_id"], "U001")
        self.assertNotIn("_supabase_user_id", record)

    def test_health_retains_compatibility_fields_and_reports_database(self):
        main.DATABASE_SOURCE = "supabase"
        result = main.health()
        self.assertEqual(result["status"], "ok")
        self.assertFalse(result["demo_mode"])
        self.assertEqual(result["database"], "supabase")

    def test_supabase_unavailable_uses_csv_fallback(self):
        expected = ([], [], [], [])
        result = main.load_runtime_catalog(database_loader=lambda: (_ for _ in ()).throw(ConnectionError()), csv_loader=lambda: expected)
        self.assertEqual(result, expected)
        self.assertEqual(main.DATABASE_SOURCE, "csv_fallback")

    def test_supabase_available_becomes_primary_catalog(self):
        result = main.load_runtime_catalog(database_loader=lambda: database.load_catalog(self.client), csv_loader=lambda: self.fail("CSV fallback should not load"))
        self.assertEqual(len(result[0]), 40)
        self.assertEqual(main.DATABASE_SOURCE, "supabase")

    def test_database_document_lookup_filters_by_uuid_and_omits_private_key(self):
        documents = database.documents_for_user("uuid-001", self.client)
        self.assertTrue(documents)
        self.assertTrue(all(row["id"] in {f"doc-{i:03}" for i in range(110)} for row in documents))
        self.assertNotIn("private_storage_key", documents[0])

    def test_unknown_eligibility_attribute_stays_unknown(self):
        self.assertEqual(main.evaluate({"field": "disability_status", "operator": "==", "value": True}, {"age": 25}), "UNKNOWN")

    def test_existing_recommendation_handler_returns_matches(self):
        profile = main.normalized_db_profile(database.profile_by_demo_id("U001", self.client))
        response = TestClient(main.app).post("/api/schemes/recommend", json={"profile": profile, "query": "student education support"})
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertIn("recommendations", result)
        self.assertTrue(result["recommendations"])

    def test_upload_metadata_does_not_require_storage_and_is_not_public(self):
        saved = database.add_user_document("uuid-001", "income.txt", "text/plain", "NEEDS_REVIEW", self.client)
        self.assertEqual(saved["private_storage_key"], "local-processing-only://metadata")
        public = database.documents_for_user("uuid-001", self.client)
        self.assertNotIn("private_storage_key", public[0])


if __name__ == "__main__":
    unittest.main()
