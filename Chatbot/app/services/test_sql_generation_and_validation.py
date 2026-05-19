import unittest
import re


class _DummyLLM:
    def generate(self, prompt: str, model=None, options=None) -> str:  # pragma: no cover
        return ""

    def chat(self, prompt: str, session=None) -> str:  # pragma: no cover
        return ""


class TestSQLGenerationAndValidation(unittest.TestCase):
    def test_rules_allow_list_patients_with_filter(self):
        from app.services.rules import BusinessRulesService

        rules = BusinessRulesService()
        allowed, err = rules.check_query_restrictions(
            user_message="list patients with unknown name",
            sql_query=None,
            entities={},
            is_specific=False,
        )
        self.assertTrue(allowed, msg=err)

    def test_sql_generation_recent_appointments_uses_patient_encounters_without_inner_join(self):
        from app.services.sql_generation import SQLGenerationService

        svc = SQLGenerationService(llm_client=_DummyLLM())
        sql = svc.generate_sql("u101", "List recent appointments")
        sql_l = sql.lower()

        self.assertIn("from patient_encounters", sql_l)
        self.assertTrue(sql.strip().endswith(";"))
        self.assertIsNone(re.search(r"(?<!left )\\bjoin\\s+patients\\b", sql_l))

    def test_sql_generation_unknown_name_uses_patients_template(self):
        from app.services.sql_generation import SQLGenerationService

        svc = SQLGenerationService(llm_client=_DummyLLM())
        sql = svc.generate_sql("u101", "list patients with unknown name")
        sql_l = sql.lower()

        self.assertIn("from patients", sql_l)
        self.assertIn("where", sql_l)
        self.assertIn("is_unknown", sql_l)
        self.assertIn("limit", sql_l)
        self.assertTrue(sql.strip().endswith(";"))

    def test_sql_generation_primary_diagnosis_uses_valid_schema_columns(self):
        from app.services.sql_generation import SQLGenerationService

        svc = SQLGenerationService(llm_client=_DummyLLM())
        sql = svc.generate_sql("u101", "list of patients with migraine as primary diagnosis")
        sql_l = sql.lower()

        # Must not hallucinate icd_diagnosis.description
        self.assertNotIn("icd_diagnosis where description", sql_l)
        self.assertTrue(sql.strip().endswith(";"))

        # Prefer legacy diagnosis table when present in schema
        self.assertIn("from ap_patient_diagnose", sql_l)
        self.assertIn("join ap_lov_values", sql_l)
        self.assertIn("diag_typ_primary", sql_l)
        self.assertIn("order by diagnosed_date", sql_l)

    def test_sql_generation_gender_and_blood_type_uses_ap_patient_lovs(self):
        from app.services.sql_generation import SQLGenerationService

        svc = SQLGenerationService(llm_client=_DummyLLM())
        sql = svc.generate_sql("u101", "list all female with blood type O")
        sql_l = sql.lower()

        self.assertIn("from ap_patient", sql_l)
        self.assertIn("ap_lov_values", sql_l)
        self.assertIn("gender_lkey", sql_l)
        self.assertIn("blood_group_lkey", sql_l)
        self.assertNotIn("from patients", sql_l)
        self.assertTrue(sql.strip().endswith(";"))

    def test_sql_generation_uses_lab_template(self):
        from app.services.sql_generation import SQLGenerationService

        svc = SQLGenerationService(llm_client=_DummyLLM())
        sql = svc.generate_sql("u101", "Is there any pending lab request?")

        self.assertIn("from ap_diagnostic_orders", sql.lower())
        self.assertIn("lab_status", sql.lower())
        self.assertTrue(sql.strip().endswith(";"))

    def test_sql_generation_mrn_lab_template_respects_join_limit(self):
        from app.services.sql_generation import SQLGenerationService
        from app.services.rules import BusinessRulesService

        svc = SQLGenerationService(llm_client=_DummyLLM())
        message = "Give me a list of all lab results and requests for MRN P104."
        sql = svc.generate_sql("u101", message)

        self.assertIn("from patients", sql.lower())
        self.assertIn("ap_diagnostic_orders", sql.lower())
        self.assertIn("ap_diagnostic_order_tests_result", sql.lower())
        self.assertNotIn("ap_patient", sql.lower())
        self.assertNotIn("ap_lov_values", sql.lower())

        join_count = len(re.findall(r"\bjoin\b", sql.lower()))
        self.assertLessEqual(join_count, 3, msg=f"JOIN count too high: {join_count}\n{sql}")

        rules = BusinessRulesService()
        allowed, rule_error = rules.check_query_restrictions(
            user_message=message,
            sql_query=sql,
            entities={"medical_record_number": "P104"},
            is_specific=True,
        )
        self.assertTrue(allowed, msg=rule_error)

    def test_validator_rejects_wrong_alias_column(self):
        from app.services.validation import ValidationService

        svc = ValidationService()
        res = svc.validate_and_execute(
            "u101",
            "SELECT pe.key AS encounter_key FROM patient_encounters pe LIMIT 1;",
        )
        self.assertFalse(res.get("valid"))
        self.assertIn("pe.key", (res.get("message") or "").lower())

    def test_validator_rejects_unresolved_placeholders(self):
        from app.services.validation import ValidationService

        svc = ValidationService()
        res = svc.validate_and_execute(
            "u101",
            "SELECT 1 FROM patients p WHERE p.id = %s LIMIT 1;",
        )
        self.assertFalse(res.get("valid"))
        self.assertIn("placeholder", (res.get("message") or "").lower())

    def test_chat_orchestrator_injects_mrn_from_session(self):
        from app.services.chat_orchestrator import ChatOrchestratorService

        orch = ChatOrchestratorService.__new__(ChatOrchestratorService)
        sql, err = orch._inject_known_values_into_sql(
            "SELECT 1 FROM patients p WHERE CAST(p.medical_record_number AS TEXT) = %s LIMIT 1;",
            session={"last_patient_mrn": "P104"},
            entities={},
            is_specific=True,
        )
        self.assertIsNone(err)
        self.assertNotIn("%s", sql)
        self.assertIn("CAST(p.medical_record_number AS TEXT) = 'P104'", sql)

    def test_session_store_fallback_persists(self):
        from app.infrastructure.session_store import SessionStore

        store = SessionStore.__new__(SessionStore)
        store._connected = False
        store._client = None
        store._use_fallback = True
        store.ttl_seconds = 60

        sid = "test_session_fallback"
        store.delete(sid)
        store.set(sid, {"last_patient_mrn": "P104"})
        loaded = store.get(sid)
        self.assertEqual(loaded.get("last_patient_mrn"), "P104")
        store.delete(sid)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
