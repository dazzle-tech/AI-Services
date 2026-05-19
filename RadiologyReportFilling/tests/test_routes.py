"""Tests for Medical Imaging Assist API routes."""
import os
from unittest.mock import patch

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test-fake-key-for-testing-only")
os.environ.setdefault("PERSIST_OUTPUT", "false")

from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402
import app.api.routes as routes_module  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_service_singleton():
    """Ensure each test starts with a fresh service singleton."""
    routes_module._service = None
    yield
    routes_module._service = None


@pytest.fixture
def client():
    return TestClient(app)


# ---------- Basic ----------


def test_root_returns_service_info(client):
    """GET / returns service identity and version."""
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "medical-imaging-assist"
    assert "version" in body
    assert body["docs"] == "/docs"


def test_health_returns_healthy(client):
    """GET /api/v1/health reports healthy when files load."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in ("healthy", "degraded")
    assert body["service"] == "medical-imaging-assist"
    assert body["openai_configured"] is True


def test_terms_summary_counts(client):
    """GET /api/v1/terms/summary returns non-zero counts from the sample data."""
    response = client.get("/api/v1/terms/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["icd10_count"] >= 30
    assert body["radlex_count"] >= 30
    assert body["embeddings_present"] in (True, False)


# ---------- Validation ----------


def test_report_correction_validation_error(client):
    """Missing required fields returns 422."""
    response = client.post("/api/v1/report-correction", json={"doctor_notes": "x"})
    assert response.status_code == 422


def test_analysis_matching_validation_error(client):
    """Missing required fields returns 422."""
    response = client.post("/api/v1/analysis-matching", json={"clinical_report": "x"})
    assert response.status_code == 422


# ---------- TC_001: Endpoint 1 -- Laterality conflict ----------


_TC001_MOCK_RAW = {
    "study_metadata": {
        "PatientID": "12345",
        "Modality": "CR",
        "BodyPartExamined": "CHEST",
        "ViewPosition": "PA",
        "StudyDate": "20260513",
    },
    "exam_type": "Chest X-ray PA/Lateral",
    "corrected_doctor_notes": (
        "Patient presenting with acute chest pain and persistent cough. "
        "Suspected left-sided pneumonia."
    ),
    "corrected_radiologist_notes": (
        "PA/Lateral Chest: Consolidation and opacity noted in the right lower lobe. "
        "No evidence of pneumothorax."
    ),
    "structured_report": {
        "indication": "Acute chest pain, persistent cough; suspected pneumonia",
        "technique": "PA and lateral chest radiographs",
        "findings": [
            {"label": "Consolidation", "location": "Right lower lobe"},
            {"label": "Pneumothorax", "status": "absent"},
        ],
        "impression": "Right lower lobe consolidation; clinical suspicion was for left-sided pneumonia.",
    },
    "spelling_corrections": {},
    "findings": [
        {"label": "Consolidation", "location": "Right lower lobe", "source": "radiologist"},
    ],
    "warnings": [],
    "rag_grounding": {
        "icd10_codes": [
            {"code": "J18.9", "term": "Pneumonia, unspecified organism", "matched_phrase": "pneumonia"}
        ],
        "radlex_terms": [
            {"id": "RID4853", "term": "consolidation", "matched_phrase": "consolidation"},
            {"id": "RID28494", "term": "right lower lobe", "matched_phrase": "right lower lobe"},
        ],
    },
}


def test_tc001_laterality_conflict(client):
    """TC_001: doctor says left, radiologist says right -- LATERALITY_CONFLICT must fire."""
    payload = {
        "doctor_notes": (
            "Patient presenting with acute chest pain and persistent cough. "
            "Suspected left-sided pneumonia."
        ),
        "radiologist_notes": (
            "PA/Lateral Chest: Consolidation and opacity noted in the right lower lobe. "
            "No evidence of pneumothorax."
        ),
        "exam_type": "Chest X-ray 2 Views",
        "extracted_dicom_metadata": {
            "PatientID": "12345",
            "Modality": "CR",
            "BodyPartExamined": "CHEST",
            "ViewPosition": "PA",
            "StudyDate": "20260513",
        },
    }
    with patch(
        "app.services.medical_service.MedicalAIClient.analyze",
        return_value=_TC001_MOCK_RAW,
    ):
        response = client.post("/api/v1/report-correction", json=payload)

    assert response.status_code == 200, response.text
    body = response.json()

    # Envelope present
    assert "raw_model_output" in body
    assert "safety_normalized_output" in body
    assert "disclaimer" in body
    assert body["disclaimer"].startswith("This output is for assistive purposes only")

    sn = body["safety_normalized_output"]
    codes = {w["code"] for w in sn["warnings"]}
    assert "LATERALITY_CONFLICT" in codes, f"Expected LATERALITY_CONFLICT in {codes}"

    # Confidence dropped to Low due to laterality conflict
    assert sn["confidence"] == "Low"
    # Single PA view -> no critical alert just from this
    assert sn["critical_alert"] is False
    # Findings preserved
    assert any("Consolidation" == f["label"] for f in sn["findings"])
    # RAG grounding present
    assert any(item["code"] == "J18.9" for item in sn["rag_grounding"]["icd10_codes"])


# ---------- TC_004: Endpoint 2 -- Hierarchy of Truth ----------


_TC004_MOCK_RAW = {
    "study_metadata": {
        "Modality": "DX",
        "ViewPosition": "PA",
        "StudyDescription": "CHEST SINGLE VIEW",
    },
    "exam_type": "Chest X-ray PA (single view)",
    "reconciled_findings": [
        {
            "label": "Pulmonary nodule",
            "location": "Left upper lobe",
            "size_cm": 1.2,
            "source": "clinical_report",
            "stability": "stable",
            "ai_variance": {
                "ai_size_mm": 18,
                "delta_mm": 6,
                "note": "AI measured 1.8cm; clinical report (authoritative) records 1.2cm.",
            },
        }
    ],
    "ai_findings_dropped": [],
    "ai_findings_used_for_enrichment": [],
    "findings": [
        {
            "label": "Pulmonary nodule",
            "location": "Left upper lobe",
            "size_cm": 1.2,
            "source": "reconciled",
        }
    ],
    "warnings": [
        {
            "severity": "high",
            "code": "AI_SIZE_VARIANCE",
            "message": (
                "AI nodule size (18mm) differs from clinical report (12mm). Clinical "
                "report retained per hierarchy-of-truth."
            ),
        }
    ],
    "rag_grounding": {
        "icd10_codes": [
            {"code": "R91.1", "term": "Solitary pulmonary nodule", "matched_phrase": "pulmonary nodule"}
        ],
        "radlex_terms": [
            {"id": "RID3875", "term": "pulmonary nodule", "matched_phrase": "nodule"},
            {"id": "RID1325", "term": "left upper lobe", "matched_phrase": "left upper lobe"},
        ],
    },
}


def test_tc004_hierarchy_of_truth(client):
    """TC_004: Doctor says 1.2cm, AI says 1.8cm. Doctor's value retained; AI variance recorded."""
    payload = {
        "clinical_report": (
            "Follow-up of pulmonary nodule. A stable 1.2cm nodule is noted in the left upper lobe."
        ),
        "ai_image_analysis": {
            "findings": [
                {
                    "label": "Nodule",
                    "location": "Left Upper Lobe",
                    "size_mm": 18,
                    "confidence": 0.92,
                }
            ]
        },
        "extracted_dicom_metadata": {
            "Modality": "DX",
            "ViewPosition": "PA",
            "StudyDescription": "CHEST SINGLE VIEW",
        },
    }
    with patch(
        "app.services.medical_service.MedicalAIClient.analyze",
        return_value=_TC004_MOCK_RAW,
    ):
        response = client.post("/api/v1/analysis-matching", json=payload)

    assert response.status_code == 200, response.text
    body = response.json()
    sn = body["safety_normalized_output"]

    # Final finding uses doctor's 1.2cm, NOT AI's 1.8cm
    nodule_findings = [f for f in sn["findings"] if "Nodule" in f["label"] or "nodule" in f["label"]]
    assert nodule_findings, "Expected at least one nodule finding"
    assert nodule_findings[0]["size_cm"] == 1.2

    # AI_SIZE_VARIANCE warning surfaced
    codes = {w["code"] for w in sn["warnings"]}
    assert "AI_SIZE_VARIANCE" in codes

    # AI variance recorded in reconciled_findings
    reconciled = sn["reconciled_findings"]
    assert reconciled is not None
    assert reconciled[0]["ai_variance"]["ai_size_mm"] == 18

    # Confidence not High (variance warning present), no critical alert
    assert sn["confidence"] in ("Medium", "Low")
    assert sn["critical_alert"] is False
    assert body["disclaimer"].startswith("This output is for assistive purposes only")
