"""Tests for the radiology report filling API routes."""
import os
from unittest.mock import patch

import httpx
import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test-fake-key-for-testing-only")
os.environ.setdefault("PERSIST_OUTPUT", "false")

from main import app  # noqa: E402
import app.api.routes as routes_module  # noqa: E402

pytestmark = pytest.mark.anyio


@pytest.fixture(autouse=True)
def _reset_service_singleton():
    """Ensure each test starts with a fresh service singleton."""
    routes_module._service = None
    yield
    routes_module._service = None


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client


_EXPECTED_RESPONSE_FIELDS = {
    "ID",
    "TEMPLATE_NAME",
    "TEMPLATE_TEXT",
    "STATUS_ID",
    "CREATED_BY",
    "CREATION_DATETIME",
    "DELETED_BY",
    "DELETE_DATETIME",
    "UPDATED_BY",
    "UPDATE_DATETIME",
    "Physician",
}

_OLD_RESPONSE_FIELDS = {
    "DICOM",
    "OutputLanguage",
    "raw_model_output",
    "safety_normalized_output",
    "findings",
    "warnings",
    "rag_grounding",
    "reconciled_findings",
    "corrected_doctor_notes",
    "corrected_radiologist_notes",
    "structured_report",
    "AIInterpretation",
    "QCResult",
    "DoctorNotes",
    "RadiologistNotes",
    "ExamType",
}

_GREEK_ABDOMEN_PAYLOAD = {
    "PatientID": "P12345",
    "PatientName": "John Doe",
    "OrderID": "ORD-001",
    "OrderDate": "2026-06-04T00:00:00",
    "DateOfBirth": "1980-01-15T00:00:00",
    "NationalID": "123456789",
    "Gender": "Male",
    "AccessionNumber": "ACC-10008",
    "OutputLanguage": "el",
    "ExamType": "ΥΠΕΡΗΧΟΓΡΑΦΗΜΑ ΑΝΩ ΚΑΙ ΚΑΤΩ ΚΟΙΛΙΑΣ",
    "DoctorNotes": "",
    "RadiologistNotes": "",
    "DICOM": {
        "Modality": "US",
        "BodyPartExamined": "ABDOMEN",
        "StudyDate": "20260604",
    },
}

_PORTUGUESE_ABDOMEN_PAYLOAD = {
    "PatientID": "P12345",
    "PatientName": "John Doe",
    "OrderID": "ORD-001",
    "OrderDate": "2026-06-04T00:00:00",
    "DateOfBirth": "1980-01-15T00:00:00",
    "NationalID": "123456789",
    "Gender": "Male",
    "AccessionNumber": "ACC-10008",
    "OutputLanguage": "pt",
    "ExamType": "Ecografia abdominal",
    "DoctorNotes": "",
    "RadiologistNotes": "",
    "DICOM": {
        "Modality": "US",
        "BodyPartExamined": "ABDOMEN",
        "StudyDate": "20260604",
    },
}

_COMPACT_WORKFLOW_PAYLOAD = {
    "PatientID": "LIDC-IDRI-0001",
    "PatientName": "John Doe",
    "OrderID": "ORD-001",
    "OrderDate": "2026-06-04T00:00:00",
    "DateOfBirth": "1980-01-15T00:00:00",
    "NationalID": "123456789",
    "Gender": "Male",
    "AccessionNumber": "ACC-10008",
    "OutputLanguage": "el",
    "ExamType": "CHEST",
    "DoctorNotes": "Patient presenting with acute chest pain and persistent cough. Suspected left-sided pneumonia.",
    "RadiologistNotes": "PA/Lateral Chest: Consolidation and opacity noted in the right lower lobe. No evidence of pneumothorax.",
    "SigningPhysician": None,
    "SigningPhysicianCode": None,
    "AIInterpretationSummary": {
        "status": "REVIEW_REQUIRED",
        "critical_alert": False,
        "summary": "Η εκτέλεση του μοντέλου ερμηνείας ακτινογραφίας απέτυχε. Απαιτείται αξιολόγηση από ακτινολόγο.",
        "findings_count": 0,
        "warnings": ["Vision model request timed out after 30s. Service returned REVIEW_REQUIRED."],
    },
    "QC": {
        "qc_status": "REVIEW_REQUIRED",
        "issue_type": "MISSING_METADATA",
        "recommended_action": "Επαληθεύστε τα μεταδεδομένα DICOM (λείπει το ViewPosition).",
        "human_review_required": True,
        "confidence": 0.6,
    },
    "DICOM": {
        "Modality": "DX",
        "BodyPartExamined": "CHEST",
        "StudyDate": "20000101",
        "ViewPosition": None,
        "StudyInstanceUID": "1.2.276.0.7230010.3.1.2.3864760610.2128.1780568219.775",
        "DICOMAccessionNumber": "ACC-10008",
    },
}

_LEGACY_AI_BLOCK_EN = "Additional" + " AI" + " findings:"
_LEGACY_AI_BLOCK_EL = "Λοιπά" + " ευρήματα" + " AI:"
_MISMATCH_WARNING_TITLE = "⚠ WARNING: DICOM/ORDER MISMATCH"
_MISMATCH_WARNING_SEPARATOR = "─────────────────────────────────────────────────"


async def test_root_returns_service_info(client):
    """GET / returns service identity and version."""
    response = await client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "medical-imaging-assist"
    assert "version" in body
    assert body["docs"] == "/docs"


async def test_health_returns_healthy(client):
    """GET /api/v1/health reports healthy when files load."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in ("healthy", "degraded")
    assert body["service"] == "medical-imaging-assist"
    assert body["openai_configured"] is True


async def test_terms_summary_counts(client):
    """GET /api/v1/terms/summary returns non-zero counts from the sample data."""
    response = await client.get("/api/v1/terms/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["icd10_count"] >= 30
    assert body["radlex_count"] >= 30
    assert body["embeddings_present"] in (True, False)


async def test_report_correction_restores_workflow_contract(client):
    """POST /api/v1/report-correction returns workflow-safe clinical report text."""
    payload = {
        "doctor_notes": "Suspected left-sided pneumonia with cough.",
        "radiologist_notes": "Right lower lobe consolidation is present.",
        "exam_type": "Chest X-ray 2 Views",
        "extracted_dicom_metadata": {"Modality": "CR"},
    }

    response = await client.post("/api/v1/report-correction", json=payload)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["clinical_report_text"] == "Right lower lobe consolidation is present."
    assert body["confirmed"] is False
    assert any(w["code"] == "LATERALITY_CONFLICT" for w in body["warnings"])
    assert body["safety_normalized_output"]["clinical_report"] == body["clinical_report_text"]
    assert "icd10_codes" in body["safety_normalized_output"]["rag_grounding"]


async def test_analysis_matching_restores_workflow_contract(client):
    """POST /api/v1/analysis-matching returns reconciled findings and ICD-10 suggestions."""
    payload = {
        "clinical_report": "Right lower lobe consolidation is present. No evidence of pneumothorax.",
        "ai_image_analysis": {
            "findings": [
                {
                    "finding_code": "PNEUMONIA",
                    "finding_text": "Right lower lobe consolidation",
                    "location": "right lower lobe",
                    "confidence": 0.94,
                },
                {
                    "finding_code": "PNEUMOTHORAX",
                    "finding_text": "Pneumothorax",
                    "location": "right chest",
                    "confidence": 0.71,
                },
            ]
        },
        "extracted_dicom_metadata": {"Modality": "CR", "ViewPosition": "PA"},
    }

    response = await client.post("/api/v1/analysis-matching", json=payload)

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["reconciled_findings"]) == 2
    assert body["reconciled_findings"][0]["match_status"] in {"matched", "partial"}
    assert body["reconciled_findings"][1]["match_status"] == "unmatched"
    assert body["suggested_icd10_codes"]
    assert body["safety_normalized_output"]["reconciled_findings"] == body["reconciled_findings"]


async def test_report_filling_requires_accession_number(client):
    """AccessionNumber is the only required public request field."""
    response = await client.post("/api/v1/report-filling", json={"PatientID": "P12345"})
    assert response.status_code == 422


async def test_report_filling_greek_abdominal_ultrasound_template(client):
    """Greek abdominal ultrasound returns the stored template without AI generation."""
    with patch("app.services.medical_service.MedicalAIClient.analyze") as mock_analyze:
        response = await client.post("/api/v1/report-filling", json=_GREEK_ABDOMEN_PAYLOAD)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["TEMPLATE_NAME"] == "ΥΠΕΡΗΧΟΓΡΑΦΗΜΑ ΑΝΩ ΚΑΙ ΚΑΤΩ ΚΟΙΛΙΑΣ"
    assert "Ήπαρ φυσιολογικού μεγέθους" in body["TEMPLATE_TEXT"]
    assert "Ο ΙΑΤΡΟΣ ΑΚΤΙΝΟΛΟΓΟΣ" in body["TEMPLATE_TEXT"]
    assert "______________________" in body["TEMPLATE_TEXT"]
    assert body["Physician"] is None
    mock_analyze.assert_not_called()


async def test_report_filling_uses_runtime_signing_physician_when_provided(client):
    """Provided signing physician fields should populate the report signature."""
    payload = {
        **_GREEK_ABDOMEN_PAYLOAD,
        "SigningPhysician": "ΙΑΤΡΟΣ ΔΟΚΙΜΗ",
        "SigningPhysicianCode": "LIC-2026-01",
    }

    response = await client.post("/api/v1/report-filling", json=payload)

    assert response.status_code == 200, response.text
    body = response.json()
    assert "ΙΑΤΡΟΣ ΔΟΚΙΜΗ" in body["TEMPLATE_TEXT"]
    assert "(κωδικός: LIC-2026-01)" in body["TEMPLATE_TEXT"]
    assert body["Physician"] == "ΙΑΤΡΟΣ ΔΟΚΙΜΗ"


async def test_report_filling_greek_kidney_ultrasound_template(client):
    """Greek kidney ultrasound selects the kidney-specific stored template."""
    payload = {
        "AccessionNumber": "ACC-KIDNEY-01",
        "OutputLanguage": "el",
        "DICOM": {"Modality": "US", "BodyPartExamined": "KIDNEY"},
    }
    response = await client.post("/api/v1/report-filling", json=payload)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["TEMPLATE_NAME"] == "ΥΠΕΡΗΧΟΓΡΑΦΗΜΑ ΝΕΦΡΩΝ"
    assert "επινεφριδικών περιοχών" in body["TEMPLATE_TEXT"]


async def test_report_filling_greek_kub_ultrasound_template(client):
    """Greek KUB ultrasound selects the combined urinary tract template."""
    payload = {
        "AccessionNumber": "ACC-KUB-01",
        "OutputLanguage": "el",
        "ExamType": "ΥΠΕΡΗΧΟΓΡΑΦΗΜΑ ΝΕΦΡΩΝ—ΟΥΡΗΤΗΡΩΝ—ΟΥΡΟΔΟΧΟΥ ΚΥΣΤΕΩΣ—ΠΡΟΣΤΑΤΟΥ",
        "DICOM": {"Modality": "US", "BodyPartExamined": "KIDNEY,BLADDER,PROSTATE"},
    }
    response = await client.post("/api/v1/report-filling", json=payload)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["TEMPLATE_NAME"] == "ΥΠΕΡΗΧΟΓΡΑΦΗΜΑ ΝΕΦΡΩΝ—ΟΥΡΗΤΗΡΩΝ—ΟΥΡΟΔΟΧΟΥ ΚΥΣΤΕΩΣ—ΠΡΟΣΤΑΤΟΥ"
    assert "Φλοιώδεις κύστεις νεφρών άμφω" in body["TEMPLATE_TEXT"]


async def test_report_filling_portuguese_abdominal_ultrasound_template(client):
    """Portuguese abdominal ultrasound returns the stored Portuguese template."""
    response = await client.post("/api/v1/report-filling", json=_PORTUGUESE_ABDOMEN_PAYLOAD)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["TEMPLATE_NAME"] == "Ecografia abdominal"
    assert body["TEMPLATE_TEXT"].startswith("Fígado: tamanho e ecoestrutura normal")
    assert "Não alterações ecográficas de urgências" in body["TEMPLATE_TEXT"]


async def test_report_filling_defaults_output_language_to_greek(client):
    """Missing OutputLanguage defaults to Greek stored templates."""
    payload = {
        "AccessionNumber": "ACC-10008",
        "DICOM": {"Modality": "US", "BodyPartExamined": "ABDOMEN"},
    }
    response = await client.post("/api/v1/report-filling", json=payload)

    assert response.status_code == 200, response.text
    assert response.json()["TEMPLATE_NAME"] == "ΥΠΕΡΗΧΟΓΡΑΦΗΜΑ ΑΝΩ ΚΑΙ ΚΑΤΩ ΚΟΙΛΙΑΣ"


async def test_report_filling_rejects_unknown_output_language(client):
    """Unsupported OutputLanguage values return a clear 422 validation error."""
    payload = {
        "AccessionNumber": "ACC-2026-0001",
        "OutputLanguage": "fr",
    }

    response = await client.post("/api/v1/report-filling", json=payload)

    assert response.status_code == 422
    assert "OutputLanguage" in response.text


async def test_report_filling_preserves_line_breaks_and_greek_characters(client):
    """TEMPLATE_TEXT keeps Greek characters, headings, and line breaks intact."""
    response = await client.post("/api/v1/report-filling", json=_GREEK_ABDOMEN_PAYLOAD)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["TEMPLATE_NAME"] == "ΥΠΕΡΗΧΟΓΡΑΦΗΜΑ ΑΝΩ ΚΑΙ ΚΑΤΩ ΚΟΙΛΙΑΣ"
    assert "\n\nΟ ΙΑΤΡΟΣ ΑΚΤΙΝΟΛΟΓΟΣ\n\n" in body["TEMPLATE_TEXT"]
    assert "Ήπαρ φυσιολογικού μεγέθους" in body["TEMPLATE_TEXT"]
    assert "—" in body["TEMPLATE_TEXT"] or "______________________" in body["TEMPLATE_TEXT"]


async def test_report_filling_response_contains_only_new_fields(client):
    """The response exposes only the template-only response contract."""
    response = await client.post("/api/v1/report-filling", json=_GREEK_ABDOMEN_PAYLOAD)

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body.keys()) == _EXPECTED_RESPONSE_FIELDS
    for field in _OLD_RESPONSE_FIELDS:
        assert field not in body
    assert body["TEMPLATE_TEXT"]


async def test_report_filling_adapts_template_when_clinical_context_present(client):
    """AI is used only to adapt the selected stored template when notes are present."""
    payload = {
        **_GREEK_ABDOMEN_PAYLOAD,
        "RadiologistNotes": "Ήπαρ με αυξημένη ηχογένεια.",
    }
    mock_ai_output = {
        "ID": 0,
        "TEMPLATE_NAME": "ΥΠΕΡΗΧΟΓΡΑΦΗΜΑ ΑΝΩ ΚΑΙ ΚΑΤΩ ΚΟΙΛΙΑΣ",
        "TEMPLATE_TEXT": (
            "ΥΠΕΡΗΧΟΓΡΑΦΗΜΑ ΑΝΩ ΚΑΙ ΚΑΤΩ ΚΟΙΛΙΑΣ\n\n"
            "Ήπαρ με αυξημένη ηχογένεια.\n\n"
            "Ο ΙΑΤΡΟΣ ΑΚΤΙΝΟΛΟΓΟΣ\n\n"
            "______________________"
        ),
        "Physician": None,
    }
    with patch(
        "app.services.medical_service.MedicalAIClient.analyze",
        return_value=mock_ai_output,
    ) as mock_analyze:
        response = await client.post("/api/v1/report-filling", json=payload)

    assert response.status_code == 200, response.text
    body = response.json()
    assert "αυξημένη ηχογένεια" in body["TEMPLATE_TEXT"]
    user_prompt = mock_analyze.call_args.args[1]
    assert "BASE_TEMPLATE:" in user_prompt
    assert "Ήπαρ φυσιολογικού μεγέθους" in user_prompt


async def test_report_filling_merges_ai_findings_into_findings_for_any_exam_type(client):
    """AIInterpretation.findings should appear once in Findings, without a duplicate AI block."""
    payload = {
        **_GREEK_ABDOMEN_PAYLOAD,
        "ExamType": "XR_CHEST",
        "AIInterpretation": {
            "findings": [
                {"finding_text": "Possible low-confidence lung opacity. Radiologist review required."},
                {"finding_text": "Small pleural effusion cannot be excluded."},
            ]
        },
    }
    mock_ai_output = {
        "ID": 0,
        "TEMPLATE_NAME": "ΑΚΤΙΝΟΛΟΓΙΚΗ ΕΚΘΕΣΗ",
        "TEMPLATE_TEXT": (
            "ΑΚΤΙΝΟΛΟΓΙΚΗ ΕΚΘΕΣΗ\n\n"
            "Κλινική ένδειξη:\n"
            "Δεν αναφέρεται.\n\n"
            "Τεχνική:\n"
            "Η εξέταση εκτελέστηκε σύμφωνα με το πρότυπο πρωτόκολλο του τμήματος.\n\n"
            "Ευρήματα:\n"
            "Δεν παρατηρούνται εστιακές παθολογικές αλλοιώσεις.\n\n"
            "Συμπέρασμα:\n"
            "Χωρίς οξέα ευρήματα.\n\n"
            "Ο ΙΑΤΡΟΣ ΑΚΤΙΝΟΛΟΓΟΣ\n\n"
            "______________________"
        ),
    }
    with patch(
        "app.services.medical_service.MedicalAIClient.analyze",
        return_value=mock_ai_output,
    ):
        response = await client.post("/api/v1/report-filling", json=payload)

    assert response.status_code == 200, response.text
    body = response.json()
    assert _LEGACY_AI_BLOCK_EN not in body["TEMPLATE_TEXT"]
    assert _LEGACY_AI_BLOCK_EL not in body["TEMPLATE_TEXT"]
    assert body["TEMPLATE_TEXT"].count("Possible low-confidence lung opacity. Radiologist review required.") == 1
    assert "Small pleural effusion cannot be excluded. Radiologist review required." in body["TEMPLATE_TEXT"]
    assert body["TEMPLATE_TEXT"].index("Possible low-confidence lung opacity. Radiologist review required.") < body["TEMPLATE_TEXT"].index("Συμπέρασμα:")


async def test_report_filling_greek_chest_xray_merges_qc_ai_and_radiologist_notes(client):
    """Greek chest X-ray output should prefer radiologist notes and merge QC/AI into TEMPLATE_TEXT only."""
    payload = {
        "AccessionNumber": "ACC-CHEST-01",
        "OutputLanguage": "el",
        "ExamType": "Chest X-ray 2 Views",
        "DoctorNotes": "Patient presenting with acute chest pain and persistent cough. Suspected left-sided pneumonia.",
        "RadiologistNotes": "PA/Lateral Chest: Consolidation and opacity noted in the right lower lobe. No evidence of pneumothorax.",
        "AIInterpretation": {
            "findings": [
                {
                    "finding_code": "SURGICAL_CLIPS",
                    "finding_text": "Surgical clips in the upper abdomen consistent with prior surgery.",
                    "location": "upper abdomen",
                },
                {
                    "finding_code": "DEGENERATIVE_CHANGES",
                    "finding_text": "Mild degenerative changes of the thoracic spine.",
                    "location": "thoracic spine",
                },
            ]
        },
        "QCResult": {
            "qc_status": "REVIEW_REQUIRED",
            "issue_type": "MISSING_METADATA",
            "details": {"num_images": 1},
        },
        "DICOM": {
            "Modality": "CR",
            "BodyPartExamined": "CHEST",
        },
    }
    mock_ai_output = {
        "ID": 0,
        "TEMPLATE_NAME": "ΑΚΤΙΝΟΛΟΓΙΚΗ ΕΚΘΕΣΗ",
        "TEMPLATE_TEXT": (
            "ΑΚΤΙΝΟΛΟΓΙΚΗ ΕΚΘΕΣΗ\n\n"
            "Κλινική ένδειξη:\n"
            "Patient presenting with acute chest pain and persistent cough. Suspected left-sided pneumonia.\n\n"
            "Τεχνική:\n"
            "Η εξέταση εκτελέστηκε σύμφωνα με το πρότυπο πρωτόκολλο του τμήματος.\n"
        ),
    }

    with patch(
        "app.services.medical_service.MedicalAIClient.analyze",
        return_value=mock_ai_output,
    ):
        response = await client.post("/api/v1/report-filling", json=payload)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["TEMPLATE_NAME"] == "ΑΚΤΙΝΟΓΡΑΦΙΑ ΘΩΡΑΚΟΣ 2 ΛΗΨΕΩΝ"
    assert body["TEMPLATE_TEXT"] == (
        "ΑΚΤΙΝΟΓΡΑΦΙΑ ΘΩΡΑΚΟΣ 2 ΛΗΨΕΩΝ\n\n"
        "Κλινική ένδειξη:\n"
        "Οξύ θωρακικό άλγος και επίμονος βήχας. Κλινική υποψία πνευμονίας.\n\n"
        "Τεχνική:\n"
        "Διατίθεται μία ακτινογραφική λήψη θώρακος για αξιολόγηση. Η αξιολόγηση είναι περιορισμένη λόγω απουσίας πλήρους σειράς λήψεων και ελλιπών μεταδεδομένων προβολής.\n\n"
        "Ευρήματα:\n"
        "Παρατηρείται πύκνωση-σκίαση στην προβολή του δεξιού κάτω λοβού, σύμφωνα με τις διαθέσιμες σημειώσεις.\n"
        "Δεν αναγνωρίζεται εμφανής πνευμοθώρακας.\n"
        "Απεικονίζονται χειρουργικά clips στην άνω κοιλιακή χώρα.\n"
        "Ήπιες εκφυλιστικές αλλοιώσεις της θωρακικής μοίρας της σπονδυλικής στήλης.\n\n"
        "Συμπέρασμα:\n"
        "Περιορισμένη αξιολόγηση λόγω μίας διαθέσιμης λήψης.\n"
        "Πύκνωση-σκίαση δεξιού κάτω λοβού, πιθανώς φλεγμονώδους αιτιολογίας στο κατάλληλο κλινικό πλαίσιο.\n"
        "Δεν αναγνωρίζεται εμφανής πνευμοθώρακας.\n\n"
        "Ο ΙΑΤΡΟΣ ΑΚΤΙΝΟΛΟΓΟΣ\n\n"
        "______________________"
    )
    assert body["Physician"] is None
    for field in (
        "OutputLanguage",
        "AIInterpretation",
        "QCResult",
        "DICOM",
        "findings",
        "warnings",
        "summary",
    ):
        assert field not in body


async def test_report_filling_does_not_duplicate_ai_findings_already_in_findings_section(client):
    """AI findings already present in Findings should not be rendered again anywhere else."""
    payload = {
        "AccessionNumber": "ACC-EN-01",
        "OutputLanguage": "en",
        "ExamType": "Chest X-ray",
        "AIInterpretation": {
            "findings": [
                {"finding_text": "Possible apparent enlargement of the cardiac silhouette."},
                {"finding_text": "Possible lung opacity in the left mid-lung field."},
            ]
        },
        "DICOM": {"Modality": "CR", "BodyPartExamined": "CHEST"},
    }
    mock_ai_output = {
        "ID": 0,
        "TEMPLATE_NAME": "RADIOLOGY REPORT",
        "TEMPLATE_TEXT": (
            "RADIOLOGY REPORT\n\n"
            "Findings:\n"
            "Consolidation and opacity noted in the right lower lobe.\n"
            "Possible apparent enlargement of the cardiac silhouette. Radiologist review required.\n"
            "Possible lung opacity in the left mid-lung field. Radiologist review required.\n\n"
            "Impression:\n"
            "Right lower lobe consolidation.\n"
        ),
    }

    with patch(
        "app.services.medical_service.MedicalAIClient.analyze",
        return_value=mock_ai_output,
    ):
        response = await client.post("/api/v1/report-filling", json=payload)

    assert response.status_code == 200, response.text
    body = response.json()
    assert _LEGACY_AI_BLOCK_EN not in body["TEMPLATE_TEXT"]
    assert body["TEMPLATE_TEXT"].count(
        "Possible apparent enlargement of the cardiac silhouette. Radiologist review required."
    ) == 1
    assert body["TEMPLATE_TEXT"].count(
        "Possible lung opacity in the left mid-lung field. Radiologist review required."
    ) == 1


async def test_report_filling_adds_mismatch_warning_at_top_of_report(client):
    """A DICOM/order mismatch flag in the existing DICOM context should render a top warning banner."""
    payload = {
        "AccessionNumber": "ACC-10008",
        "OutputLanguage": "en",
        "DICOM": {
            "Modality": "CR",
            "BodyPartExamined": "CHEST",
            "DICOMAccessionNumber": "ACC-10015",
            "dicom_order_mismatch": True,
        },
    }
    response = await client.post("/api/v1/report-filling", json=payload)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["TEMPLATE_TEXT"].startswith(_MISMATCH_WARNING_TITLE)
    assert body["TEMPLATE_TEXT"].splitlines()[1] == (
        "The uploaded DICOM file (ACC-10015) does not match the accession number in the order form "
        "(ACC-10008). Radiologist notes in this report may refer to a different study. Manual verification "
        "is required before this report can be finalised or signed."
    )
    assert _MISMATCH_WARNING_SEPARATOR in body["TEMPLATE_TEXT"]
    assert "RADIOLOGY REPORT" in body["TEMPLATE_TEXT"]


async def test_report_filling_omits_mismatch_warning_when_flag_is_false(client):
    """No mismatch block should appear when dicom_order_mismatch is false."""
    payload = {
        "AccessionNumber": "ACC-10008",
        "OutputLanguage": "en",
        "DICOM": {
            "Modality": "CR",
            "BodyPartExamined": "CHEST",
            "DICOMAccessionNumber": "ACC-10008",
            "dicom_order_mismatch": False,
        },
    }
    response = await client.post("/api/v1/report-filling", json=payload)

    assert response.status_code == 200, response.text
    body = response.json()
    assert _MISMATCH_WARNING_TITLE not in body["TEMPLATE_TEXT"]
    assert _MISMATCH_WARNING_SEPARATOR not in body["TEMPLATE_TEXT"]
    assert "does not match the accession number in the order form" not in body["TEMPLATE_TEXT"]


async def test_report_filling_fallback_is_full_template_style(client):
    """Unmatched exams still return a full template-style report, not a short summary."""
    payload = {
        "AccessionNumber": "ACC-FALLBACK-01",
        "OutputLanguage": "en",
        "DICOM": {"Modality": "MR", "BodyPartExamined": "BRAIN"},
    }
    response = await client.post("/api/v1/report-filling", json=payload)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["TEMPLATE_NAME"] == "RADIOLOGY REPORT"
    assert "Clinical indication:" in body["TEMPLATE_TEXT"]
    assert "Findings:" in body["TEMPLATE_TEXT"]
    assert "Impression:" in body["TEMPLATE_TEXT"]
    assert len(body["TEMPLATE_TEXT"].splitlines()) >= 8


async def test_report_filling_accepts_compact_workflow_payload_and_builds_compact_prompt(client):
    """Compact workflow payloads should trigger AI adaptation without dumping raw workflow JSON."""
    mock_ai_output = {
        "ID": 0,
        "TEMPLATE_NAME": "RADIOLOGY REPORT",
        "TEMPLATE_TEXT": (
            "RADIOLOGY REPORT\n\n"
            "Findings:\n"
            "Right lower lobe consolidation.\n\n"
            "Impression:\n"
            "Right lower lobe opacity suspicious for pneumonia.\n"
        ),
        "Physician": None,
    }
    with patch(
        "app.services.medical_service.MedicalAIClient.analyze",
        return_value=mock_ai_output,
    ) as mock_analyze:
        response = await client.post("/api/v1/report-filling", json=_COMPACT_WORKFLOW_PAYLOAD)

    assert response.status_code == 200, response.text
    system_prompt = mock_analyze.call_args.args[0]
    user_prompt = mock_analyze.call_args.args[1]
    assert "RadiologistNotes are the primary source of truth for imaging findings." in system_prompt
    assert "Never write 'No significant radiological abnormality'" in system_prompt
    assert "The Impression section must summarize the actual abnormal findings from RadiologistNotes." in system_prompt
    assert "COMPACT_REPORT_CONTEXT:" in user_prompt
    assert "Radiologist notes: PA/Lateral Chest: Consolidation and opacity noted in the right lower lobe." in user_prompt
    assert "Doctor notes: Patient presenting with acute chest pain and persistent cough." in user_prompt
    assert "AI interpretation summary: Η εκτέλεση του μοντέλου ερμηνείας ακτινογραφίας απέτυχε." in user_prompt
    assert "QC status: REVIEW_REQUIRED" in user_prompt
    assert "QC issue: MISSING_METADATA" in user_prompt
    assert "DICOM modality: DX" in user_prompt
    assert "DICOM body part: CHEST" in user_prompt
    assert "DICOM view position: missing" in user_prompt
    assert '"AIInterpretation"' not in user_prompt
    assert '"QCResult"' not in user_prompt
    assert '"DICOM"' not in user_prompt


async def test_report_filling_sanitizes_nested_ai_warning_strings(client):
    """Nested AI warning payloads should be flattened into short plain-text prompt context."""
    payload = {
        **_COMPACT_WORKFLOW_PAYLOAD,
        "AIInterpretationSummary": {
            "status": "REVIEW_REQUIRED",
            "critical_alert": False,
            "summary": "Image interpretation skipped.",
            "findings_count": 0,
            "warnings": [
                "{\"warnings\":[\"Configured model does not support multimodal/image requests.\"],\"status\":\"REVIEW_REQUIRED\"}"
            ],
        },
    }
    with patch(
        "app.services.medical_service.MedicalAIClient.analyze",
        return_value={"ID": 0, "TEMPLATE_NAME": "CHEST", "TEMPLATE_TEXT": "CHEST", "Physician": None},
    ) as mock_analyze:
        response = await client.post("/api/v1/report-filling", json=payload)

    assert response.status_code == 200, response.text
    user_prompt = mock_analyze.call_args.args[1]
    assert "AI warnings: Image interpretation failed because the configured model does not support image input." in user_prompt
    assert '"warnings"' not in user_prompt


async def test_report_filling_returns_fallback_report_when_model_returns_invalid_json(client):
    """Invalid model JSON should not surface as 422 and should fall back to radiologist notes."""
    payload = {
        **_COMPACT_WORKFLOW_PAYLOAD,
        "OutputLanguage": "en",
        "ExamType": "CHEST",
    }
    with patch(
        "app.services.medical_service.MedicalAIClient.analyze",
        side_effect=ValueError("Model returned invalid JSON: Expecting property name enclosed in double quotes"),
    ):
        response = await client.post("/api/v1/report-filling", json=payload)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["TEMPLATE_NAME"] == "CHEST"
    assert "PA/Lateral Chest: Consolidation and opacity noted in the right lower lobe. No evidence of pneumothorax." in body["TEMPLATE_TEXT"]
    assert "Automatic AI report generation failed or returned invalid JSON" in body["TEMPLATE_TEXT"]
    assert body["Physician"] is None


async def test_report_filling_rebuilds_inconsistent_english_chest_report_from_radiologist_notes(client):
    """English chest output should be rebuilt when the model impression contradicts radiologist findings."""
    payload = {
        **_COMPACT_WORKFLOW_PAYLOAD,
        "OutputLanguage": "en",
        "ExamType": "CHEST",
    }
    mock_ai_output = {
        "ID": 0,
        "TEMPLATE_NAME": "RADIOLOGY REPORT",
        "TEMPLATE_TEXT": (
            "RADIOLOGY REPORT\n\n"
            "Clinical indication:\n"
            "Acute chest pain and cough.\n\n"
            "Technique:\n"
            "Chest radiographs obtained.\n\n"
            "Findings:\n"
            "Consolidation and opacity noted.\n\n"
            "Impression:\n"
            "No significant radiological abnormality identified on the current evaluation.\n"
        ),
        "Physician": None,
    }

    with patch(
        "app.services.medical_service.MedicalAIClient.analyze",
        return_value=mock_ai_output,
    ):
        response = await client.post("/api/v1/report-filling", json=payload)

    assert response.status_code == 200, response.text
    body = response.json()
    assert "right lower lobe" in body["TEMPLATE_TEXT"].lower()
    assert "consolidation" in body["TEMPLATE_TEXT"].lower()
    assert "No evidence of pneumothorax" in body["TEMPLATE_TEXT"]
    assert "No significant radiological abnormality" not in body["TEMPLATE_TEXT"]
    assert "QC note:\nDICOM ViewPosition metadata is missing. Human review is required." in body["TEMPLATE_TEXT"]
    assert "1.2.276.0.7230010.3.1.2.3864760610.2128.1780568219.775" not in body["TEMPLATE_TEXT"]
