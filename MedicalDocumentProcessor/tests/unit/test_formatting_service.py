"""Unit tests for Step 4: structured formatting of the caller-chosen document type."""
from unittest.mock import MagicMock

import pytest

from app.models.schemas import DocumentType
from app.services.formatting_service import FormattingService


@pytest.fixture
def ai_client_stub():
    return MagicMock()


@pytest.fixture
def service(ai_client_stub):
    return FormattingService(ai_client_stub)


class TestFormattingServiceLabResult:
    def test_classifies_and_formats_lab_result(self, service, ai_client_stub):
        ai_client_stub.extract_fields.return_value = {
            "extracted_fields": {
                "test_date": "2026-08-01",
                "ordering_provider": "Dr. Hassan",
                "results": [
                    {"test_name": "WBC", "value": "11.2", "unit": "10^9/L", "reference_range": "4.0-11.0", "flag": "high"},
                ],
            },
        }

        document_type, structured_data = service.format("lab text", DocumentType.LAB_RESULT)

        assert document_type == "lab_result"
        assert structured_data["documentType"] == "lab_result"
        row = structured_data["results"][0]
        assert row["testName"] == "WBC"
        assert row["resultDate"] == "2026-08-01"
        assert row["resultValue"] == "11.2"
        assert row["normalRangeValue"] == "4.0 - 11.0"
        assert row["marker"] == "UPPER_LIMIT"
        assert row["physicianName"] == "Dr. Hassan"

    def test_plain_critical_uses_the_side_of_the_range(self, service, ai_client_stub):
        def _marker(value: str, reference: str, flag: str = "critical") -> str:
            ai_client_stub.extract_fields.return_value = {
                "extracted_fields": {
                    "results": [
                        {
                            "test_name": "Potassium",
                            "value": value,
                            "reference_range": reference,
                            "flag": flag,
                        }
                    ]
                }
            }
            _, structured = service.format("lab", DocumentType.LAB_RESULT)
            return structured["results"][0]["marker"]

        assert _marker("6.8", "3.5-5.1") == "CRITICAL_UPPER"
        assert _marker("2.1", "3.5 - 5.1") == "CRITICAL_LOWER"
        assert _marker("4.0", "3.5-5.1") == "ABNORMAL_MARKER"
        assert _marker("Positive", "Negative") == "ABNORMAL_MARKER"
        assert _marker("8", "<= 5.0") == "CRITICAL_UPPER"
        assert _marker("3", ">= 12.0") == "CRITICAL_LOWER"
        assert _marker("20", "4.0-11.0", flag="abnormal") == "ABNORMAL_MARKER"


class TestFormattingServiceRadiology:
    def test_classifies_and_formats_radiology_report(self, service, ai_client_stub):
        ai_client_stub.extract_fields.return_value = {
            "extracted_fields": {
                "study_date": "2026-07-20",
                "modality": "X-Ray",
                "body_part_examined": "Chest",
                "findings": "No acute process.",
                "impression": "Normal.",
            },
        }

        document_type, structured_data = service.format("radiology text", DocumentType.RADIOLOGY_REPORT)

        assert document_type == "radiology_report"
        report = structured_data["reports"][0]
        assert structured_data["documentType"] == "radiology_report"
        assert report["testName"] == "X-Ray Chest"
        assert report["reportDate"] == "2026-07-20"
        assert report["report"] == (
            "<p><strong>Findings:</strong> No acute process.</p>"
            "<p><strong>Impression:</strong> Normal.</p>"
        )
        assert report["severity"] is None
        assert report["radiologistInformation"] is None

    def test_radiologist_and_recommendation_are_taken_from_the_report(self, service, ai_client_stub):
        report_text = """RADIOLOGY REPORT
Radiologist: Dr. Sami Khalil, Consultant Radiologist
Referring Physician: Dr. Lina Haddad
Findings:
Patchy consolidation in the right lower lobe.
Impression:
Right lower lobe pneumonia. Moderate severity.
Recommendation: Follow-up chest X-ray in 4-6 weeks after treatment to confirm resolution.
"""
        ai_client_stub.extract_fields.return_value = {
            "extracted_fields": {
                "reports": [
                    {
                        "reportDate": "2026-10-20",
                        "testName": "Chest X-Ray, PA and Lateral",
                        "findings": "Patchy consolidation in the right lower lobe.",
                        "impression": "Right lower lobe pneumonia. Moderate severity.",
                        "severity": "MODERATE",
                        "radiologistInformation": None,
                        "radiologistComments": None,
                        "physicianName": None,
                    }
                ]
            }
        }

        _, structured_data = service.format(report_text, DocumentType.RADIOLOGY_REPORT)
        report = structured_data["reports"][0]
        assert report["radiologistInformation"] == "Dr. Sami Khalil, Consultant Radiologist"
        assert report["radiologistComments"] == (
            "Follow-up chest X-ray in 4-6 weeks after treatment to confirm resolution."
        )
        assert report["physicianName"] == "Dr. Lina Haddad"
        assert report["criticalFindings"] is None
        assert "<strong>Findings:</strong>" in report["report"]
        assert "<strong>Impression:</strong>" in report["report"]
        assert "Recommendation" not in report["report"]
        assert "Dr. Sami Khalil" not in report["report"]
        assert "Dr. Lina Haddad" not in report["report"]

    def test_report_html_includes_clinical_sections_without_patient_or_facility(self, service, ai_client_stub):
        report_text = """RADIOLOGY REPORT
Facility: Al Shifa Imaging Center
Patient: Rawan Yahya
Patient ID: 1001
Sex: Female
Date of Birth: 2004-03-02
Clinical History:
Low back pain radiating to the left leg for 3 months.
Technique:
Sagittal T1 and T2 images.
Comparison:
Lumbar spine X-ray dated 2026-08-14.
Findings:
Normal lumbar alignment.
Impression:
Mild degenerative disc changes.
Recommendation:
Clinical correlation if symptoms persist.
"""
        ai_client_stub.extract_fields.return_value = {
            "extracted_fields": {
                "reports": [
                    {
                        "findings": "short",
                        "impression": "short",
                        "report": "<p><strong>Findings:</strong> short</p>",
                    }
                ]
            }
        }

        _, structured_data = service.format(report_text, DocumentType.RADIOLOGY_REPORT)
        html_report = structured_data["reports"][0]["report"]
        assert "Low back pain radiating to the left leg" in html_report
        assert "Sagittal T1 and T2 images." in html_report
        assert "Lumbar spine X-ray dated 2026-08-14." in html_report
        assert "Normal lumbar alignment." in html_report
        assert "Mild degenerative disc changes." in html_report
        assert "Clinical correlation if symptoms persist." not in html_report
        assert "Rawan Yahya" not in html_report
        assert "Al Shifa" not in html_report
        assert "1001" not in html_report

    def test_critical_finding_is_the_impression_not_the_phone_notification(self, service, ai_client_stub):
        report_text = """FINDINGS:
The appendix is dilated (11 mm) with periappendiceal fat stranding and a 6 mm appendicolith.
IMPRESSION:
1. Acute appendicitis with appendicolith. No perforation.
CRITICAL RESULT: Communicated by phone to Dr. Omar Nasser at 14:10 on 2026-10-25.
Advice: Urgent surgical consultation.
"""
        ai_client_stub.extract_fields.return_value = {
            "extracted_fields": {
                "reports": [
                    {
                        "reportDate": "2026-10-25",
                        "testName": "CT Abdomen and Pelvis with contrast",
                        "severity": "CRITICAL",
                        "criticalFindings": "Communicated by phone to Dr. Omar Nasser at 14:10 on 2026-10-25.",
                        "radiologistComments": "Urgent surgical consultation.",
                        "physicianName": "Dr. Omar Nasser",
                        "radiologistInformation": "Dr. Hala Mansour, MD, FRCR - Consultant Radiologist",
                    }
                ]
            }
        }

        _, structured_data = service.format(report_text, DocumentType.RADIOLOGY_REPORT)
        report = structured_data["reports"][0]
        assert report["criticalFindings"] == "Acute appendicitis with appendicolith. No perforation."
        assert "Communicated by phone" not in report["criticalFindings"]
        assert "Acute appendicitis with appendicolith" in report["report"]

    def test_critical_findings_include_the_rest_of_the_report_except_the_phone_call(self, service, ai_client_stub):
        report_text = """FINDINGS:
The appendix is dilated (11 mm) with a 6 mm appendicolith.
IMPRESSION:
1. Acute appendicitis with appendicolith. No perforation.
CRITICAL FINDINGS:
Pneumoperitoneum.
Communicated by phone to Dr. Omar Nasser at 14:10 on 2026-10-25.
"""
        ai_client_stub.extract_fields.return_value = {
            "extracted_fields": {
                "reports": [
                    {
                        "severity": "CRITICAL",
                        "criticalFindings": (
                            "Pneumoperitoneum. Communicated by phone to Dr. Omar Nasser "
                            "at 14:10 on 2026-10-25."
                        ),
                    }
                ]
            }
        }

        _, structured_data = service.format(report_text, DocumentType.RADIOLOGY_REPORT)
        critical = structured_data["reports"][0]["criticalFindings"]
        assert critical == "Acute appendicitis with appendicolith. No perforation. Pneumoperitoneum."
        assert "Communicated by phone" not in critical


class TestFormattingServicePrescription:
    def test_classifies_and_formats_prescription(self, service, ai_client_stub):
        ai_client_stub.extract_fields.return_value = {
            "extracted_fields": {
                "prescription_date": "2026-08-10",
                "prescribing_provider": "Dr. Hassan",
                "medications": [
                    {"name": "Amoxicillin", "dosage": "500mg", "frequency": "TID", "route": "oral", "duration": "7 days"},
                ],
            },
        }

        document_type, structured_data = service.format("prescription text", DocumentType.PRESCRIPTION)

        assert document_type == "prescription"
        assert structured_data["medications"][0]["name"] == "Amoxicillin"


class TestFormattingServiceClinicalNote:
    def test_classifies_and_formats_clinical_note(self, service, ai_client_stub):
        ai_client_stub.extract_fields.return_value = {
            "extracted_fields": {
                "note_date": "2026-08-15",
                "author": "Dr. Hassan",
                "subjective": "Headache.",
                "assessment": "Tension headache.",
            },
        }

        document_type, structured_data = service.format("note text", DocumentType.CLINICAL_NOTE)

        assert document_type == "clinical_note"
        assert structured_data["assessment"] == "Tension headache."


class TestFormattingServiceChosenType:
    def test_discharge_summary_keeps_generic_shape_and_chosen_type(self, service, ai_client_stub):
        ai_client_stub.extract_fields.return_value = {
            "document_type": "lab_result",
            "extracted_fields": {"summary": "Discharged home."},
        }

        document_type, structured_data = service.format("summary text", DocumentType.DISCHARGE_SUMMARY)

        assert document_type == "discharge_summary"
        assert structured_data["document_type"] == "discharge_summary"
        assert structured_data["summary"] == "Discharged home."
        assert "summary text" in structured_data["content"]
        ai_client_stub.extract_fields.assert_called_once_with("summary text", "discharge_summary")

    def test_imaging_report_keeps_the_chosen_type(self, service, ai_client_stub):
        ai_client_stub.extract_fields.return_value = {
            "extracted_fields": {"modality": "MRI", "impression": "Unremarkable."},
        }

        document_type, structured_data = service.format("scan text", DocumentType.IMAGING_REPORT)

        assert document_type == "imaging_report"
        assert structured_data["documentType"] == "imaging_report"
        assert "document_type" not in structured_data
        assert structured_data["reports"][0]["testName"] == "MRI"
        assert "Impression" in structured_data["reports"][0]["report"]

    def test_missing_extracted_fields_does_not_crash(self, service, ai_client_stub):
        ai_client_stub.extract_fields.return_value = {"document_type": "prescription"}

        document_type, structured_data = service.format("text", DocumentType.LAB_RESULT)

        assert document_type == "lab_result"
        assert structured_data["documentType"] == "lab_result"
        assert structured_data["results"] == []
