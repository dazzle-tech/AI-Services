import unittest
import re
from datetime import date


class _DummyHospitalRepo:
    def __init__(self, responses=None):
        self.sqls = []
        self._responses = responses or {}

    def execute_query(self, sql: str):
        self.sqls.append(sql)
        for key, value in self._responses.items():
            if key in sql:
                return value
        return []


class _DummyAccessControlRepo:
    def __init__(self, allowed_schema):
        self._allowed_schema = allowed_schema

    def get_user_access(self, user_id: str):
        return {"allowed_schema": self._allowed_schema}


class _DummyPatientDetailsService:
    def build_patient_details_sql(self, user_id: str, patient_id: str, lookup_field: str = "id"):
        # Assert the advice path uses MRN as the external identifier.
        if lookup_field != "medical_record_number":
            raise AssertionError(f"lookup_field expected medical_record_number, got {lookup_field}")
        return "/* base_profile */ SELECT 'P104' AS medical_record_number, 'Test Person' AS full_name"

    def transform_patient_data(self, patient: dict) -> dict:
        return dict(patient or {})


class _DummyLLM:
    def generate(self, prompt: str, model=None, options=None) -> str:  # pragma: no cover
        return ""


class _DummyPatientRecordService:
    def get_patient_record_by_mrn(self, user_id: str, mrn: str):  # pragma: no cover
        return None


class _DummyPatientRecordServiceWithDate:
    def get_patient_record_by_mrn(self, user_id: str, mrn: str):  # pragma: no cover
        from app.services.patient_record import PatientRecord

        return PatientRecord(
            mrn="P104",
            demographics={
                "mrn": "P104",
                "full_name": "Test Person",
                "date_of_birth": date(2005, 2, 12),
                "sex_at_birth": "MALE",
            },
            vitals=[],
            labs=[],
            medications=[],
            allergies=[],
            visit_history=[],
            diagnoses=[],
        )


class TestAdviceMRNFlow(unittest.TestCase):
    def test_extract_mrn_formats(self):
        from app.services.mrn import extract_mrn

        self.assertEqual(extract_mrn("What advice for MRN P104?"), "P104")
        self.assertEqual(extract_mrn("Show summary for mrn p104"), "P104")
        self.assertEqual(extract_mrn("What should we do for P104?"), "P104")

    def test_extract_mrn_standalone_optional(self):
        from app.services.mrn import extract_mrn

        self.assertIsNone(extract_mrn("What should we do for P104?", allow_standalone=False))
        self.assertEqual(extract_mrn("What should we do for P104?", allow_standalone=True), "P104")

    def test_advice_detection_what_to_do(self):
        from app.services.advice import is_advice_style_question

        self.assertTrue(is_advice_style_question("what to do for patient mrn p104"))
        self.assertTrue(is_advice_style_question("What to do for MRN P104?"))
        self.assertFalse(is_advice_style_question("any advice?"))

    def test_safe_refusal_when_mrn_missing(self):
        from app.services.advice import ClinicianAdviceService

        svc = ClinicianAdviceService(
            patient_record_service=_DummyPatientRecordService(),
            llm_client=_DummyLLM(),
        )
        result = svc.handle_advice_request(user_id="u101", message="What advice should we give?")

        self.assertEqual(result.get("intent"), "advice")
        self.assertIn("include", (result.get("text") or "").lower())
        self.assertEqual((result.get("meta") or {}).get("error"), "missing_mrn")

    def test_advice_prompt_json_handles_date(self):
        from app.services.advice import ClinicianAdviceService

        svc = ClinicianAdviceService(
            patient_record_service=_DummyPatientRecordServiceWithDate(),
            llm_client=_DummyLLM(),
        )
        result = svc.handle_advice_request(user_id="u101", message="what advice for MRN P104")
        self.assertEqual(result.get("intent"), "advice")
        self.assertTrue((result.get("text") or "").strip())

    def test_spelling_correction_preserves_mrn(self):
        from app.services.correction import SpellingCorrectionService

        class _LLMReturnsDifferentMRN:
            def generate(self, prompt: str, model=None, options=None) -> str:  # pragma: no cover
                return "What to do for patient MRN P1044"

        svc = SpellingCorrectionService(llm_client=_LLMReturnsDifferentMRN())
        corrected, needs_approval = svc.correct_spelling_and_enhance_query("what to do for patient mrn p104")
        self.assertEqual(corrected, "what to do for patient mrn p104")
        self.assertFalse(needs_approval)

    def test_patient_retrieval_is_mrn_keyed(self):
        from app.services.patient_record import PatientRecordService

        allowed_schema = {
            "patients": {"columns": ["id", "medical_record_number"]},
            "ap_patient": {"columns": ["key", "patient_mrn", "is_valid"]},
        }

        dummy_repo = _DummyHospitalRepo(
            responses={
                "FROM ap_patient": [{"key": "pat001"}],
                "FROM patients": [{"id": 1001}],
                "/* base_profile */": [{"medical_record_number": "P104", "full_name": "Test Person"}],
            }
        )

        svc = PatientRecordService(
            hospital_repo=dummy_repo,
            access_control_repo=_DummyAccessControlRepo(allowed_schema),
            patient_details_service=_DummyPatientDetailsService(),
        )
        record = svc.get_patient_record_by_mrn("u101", "MRN P104")
        self.assertIsNotNone(record)

        # Ensure a MRN-filtered lookup happened and no query compares MRN to a patient_id/id field.
        joined = "\n".join(dummy_repo.sqls).lower()
        self.assertIn("medical_record_number", joined)  # MRN -> patients.id mapping query
        self.assertIn("patient_mrn", joined)  # MRN -> ap_patient.key mapping query
        self.assertIn("p104", joined)
        self.assertIsNone(re.search(r"where\\s+.*\\b(id|patient_id)\\b\\s*=\\s*'p104'", joined))


if __name__ == "__main__":
    unittest.main()
