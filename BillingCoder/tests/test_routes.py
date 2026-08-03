"""Tests for CodingAssist API routes."""
import json
import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("OPENAI_API_KEY", "sk-test-fake-key-for-testing-only")

from main import app  # noqa: E402

FIXTURES_FILE = os.path.join(os.path.dirname(__file__), "charge_request_fixtures.json")


def _load_fixture(name: str) -> dict:
    """Load a stress-test request body from tests/charge_request_fixtures.json."""
    with open(FIXTURES_FILE, "r", encoding="utf-8") as fh:
        fixtures = json.load(fh)
    key = name.replace(".json", "")
    if key not in fixtures:
        raise KeyError(f"Unknown fixture '{key}'")
    return fixtures[key]["request"]


@pytest.fixture
def client():
    """FastAPI TestClient fixture."""
    return TestClient(app)


def test_root_returns_service_info(client):
    """GET / returns 200 with service identity."""
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "CodingAssist"
    assert "version" in body


def test_health_returns_expected_fields(client):
    """GET /api/v1/health includes status, model, and RAG state fields."""
    with patch("app.api.routes.get_rag_store") as mock_rag:
        mock_rag.return_value.count.return_value = 5
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "CodingAssist"
    assert body["openai_configured"] is True
    assert "rag_term_count" in body
    assert "ptp_edit_count" in body
    assert "mue_rule_count" in body


def test_coding_edits_summary(client):
    """GET /api/v1/coding-edits/summary returns PTP/MUE counts."""
    response = client.get("/api/v1/coding-edits/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["ptp_edit_count"] > 0
    assert body["mue_rule_count"] > 0
    assert isinstance(body["ptp_edits"], list)
    assert isinstance(body["mue_limits"], list)


def test_generate_charge_validation_rejects_empty_documents(client):
    """POST /api/v1/charges/generate returns 422 when documents is empty."""
    fixture = _load_fixture("happy_path_office_visit.json")
    payload = {
        "encounter_metadata": fixture["encounter_metadata"],
        "documents": [],
    }
    response = client.post("/api/v1/charges/generate", json=payload)
    assert response.status_code == 422


def test_generate_charge_validation_rejects_malformed_administrative_fields(client):
    """POST /api/v1/charges/generate returns 422 for invalid POS/NPI before any LLM call."""
    payload = _load_fixture("invalid_structured_fields.json")
    response = client.post("/api/v1/charges/generate", json=payload)
    assert response.status_code == 422


def _rag_query_from_codes(codes: dict):
    """Build a CodingRAGStore.query side_effect that resolves known surface forms.

    `codes` maps lowercase surface form -> (code_system, code, display).
    Anything not in the map misses (returns None), forcing the live-API
    fallback path, which tests patch separately when relevant.
    """
    def _side_effect(term, code_systems=None):
        hit = codes.get(term.lower())
        if not hit:
            return None
        code_system, code, display = hit
        if code_systems and code_system not in code_systems:
            return None
        return {"term": term, "code_system": code_system, "code": code, "display": display, "source": "rag"}
    return _side_effect


def test_generate_charge_happy_path_mocked(client):
    """Clean encounter with no compliance issues drafts cleanly with zero flags."""
    payload = _load_fixture("happy_path_office_visit.json")

    fake_responses = iter([
        {"normalized_notes": "Established patient visit. Type 2 diabetes mellitus, stable. Essential hypertension, stable."},
        {"entities": [
            {"text": "type 2 diabetes mellitus", "kind": "diagnosis", "status": "confirmed", "laterality": None},
            {"text": "essential hypertension", "kind": "diagnosis", "status": "confirmed", "laterality": None},
            {"text": "office visit, established patient, moderate complexity", "kind": "procedure", "laterality": None, "units": 1},
        ]},
        {
            "charge_lines": [{
                "code_system": "CPT", "code": "99214", "description": "Office visit, established patient, moderate complexity",
                "modifiers": [], "units": 1, "linked_diagnosis_codes": ["E11.9", "I10"],
            }],
            "claim_notes": "Routine chronic-disease management visit, no issues identified.",
        },
    ])

    rag_query = _rag_query_from_codes({
        "type 2 diabetes mellitus": ("ICD-10-CM", "E11.9", "Type 2 diabetes mellitus without complications"),
        "essential hypertension": ("ICD-10-CM", "I10", "Essential (primary) hypertension"),
        "office visit, established patient, moderate complexity": ("CPT", "99214", "Office visit, established patient, moderate complexity"),
    })

    with patch(
        "app.services.coding_service.CodingAIClient.analyze",
        side_effect=lambda _s, _u: next(fake_responses),
    ), patch(
        "app.services.coding_service.CodingRAGStore.query",
        side_effect=rag_query,
    ), patch(
        "app.services.coding_service.CodingRAGStore.upsert",
        return_value=None,
    ):
        response = client.post("/api/v1/charges/generate", json=payload)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["encounter_id"] == "ENC-100234"
    assert body["compliance_flags"] == []
    assert len(body["charge_draft"]["charge_lines"]) == 1
    assert body["charge_draft"]["charge_lines"][0]["code"] == "99214"


def test_generate_charge_drops_bundled_ptp_code(client):
    """Diagnostic laparoscopy bundled into the converted-to-open appendectomy is dropped, not billed."""
    payload = _load_fixture("ncci_bundling_conflict.json")

    fake_responses = iter([
        {"normalized_notes": "Diagnostic laparoscopy converted to open appendectomy for acute appendicitis."},
        {"entities": [
            {"text": "acute appendicitis", "kind": "diagnosis", "status": "confirmed", "laterality": None},
            {"text": "open appendectomy", "kind": "procedure", "laterality": None, "units": 1},
            {"text": "diagnostic laparoscopy", "kind": "procedure", "laterality": None, "units": 1},
        ]},
        {
            "charge_lines": [
                {"code_system": "CPT", "code": "44950", "description": "Appendectomy, open", "modifiers": [], "units": 1, "linked_diagnosis_codes": ["K35.80"]},
                {"code_system": "CPT", "code": "49320", "description": "Diagnostic laparoscopy, abdomen", "modifiers": [], "units": 1, "linked_diagnosis_codes": ["K35.80"]},
            ],
            "claim_notes": "Converted procedure; both lines drafted for review.",
        },
    ])

    rag_query = _rag_query_from_codes({
        "acute appendicitis": ("ICD-10-CM", "K35.80", "Unspecified acute appendicitis"),
        "open appendectomy": ("CPT", "44950", "Appendectomy, open"),
        "diagnostic laparoscopy": ("CPT", "49320", "Diagnostic laparoscopy, abdomen, peritoneum, omentum"),
    })

    with patch(
        "app.services.coding_service.CodingAIClient.analyze",
        side_effect=lambda _s, _u: next(fake_responses),
    ), patch(
        "app.services.coding_service.CodingRAGStore.query",
        side_effect=rag_query,
    ), patch(
        "app.services.coding_service.CodingRAGStore.upsert",
        return_value=None,
    ):
        response = client.post("/api/v1/charges/generate", json=payload)

    assert response.status_code == 200, response.text
    body = response.json()
    codes = [line["code"] for line in body["charge_draft"]["charge_lines"]]
    assert codes == ["44950"]
    assert any(f["rule_type"] == "ptp_edit" and f["severity"] == "blocking" and "49320" in f["affected_codes"] for f in body["compliance_flags"])


def test_generate_charge_clamps_units_to_mue_cap(client):
    """Six same-day same-joint injections get clamped to the MUE ceiling of 1."""
    payload = _load_fixture("mue_implausible_units.json")

    fake_responses = iter([
        {"normalized_notes": "Right knee effusion. Arthrocentesis with injection performed on the right knee six times this visit."},
        {"entities": [
            {"text": "right knee effusion", "kind": "diagnosis", "status": "confirmed", "laterality": "right"},
            {"text": "knee arthrocentesis with injection", "kind": "procedure", "laterality": "right", "units": 6},
        ]},
        {
            "charge_lines": [
                {"code_system": "CPT", "code": "20610", "description": "Arthrocentesis, aspiration and/or injection, major joint", "modifiers": [], "units": 6, "linked_diagnosis_codes": ["M25.461"]},
            ],
            "claim_notes": "Repeated injections documented; flagging for review.",
        },
    ])

    rag_query = _rag_query_from_codes({
        "right knee effusion": ("ICD-10-CM", "M25.461", "Effusion, right knee"),
        "knee arthrocentesis with injection": ("CPT", "20610", "Arthrocentesis, aspiration and/or injection, major joint"),
    })

    with patch(
        "app.services.coding_service.CodingAIClient.analyze",
        side_effect=lambda _s, _u: next(fake_responses),
    ), patch(
        "app.services.coding_service.CodingRAGStore.query",
        side_effect=rag_query,
    ), patch(
        "app.services.coding_service.CodingRAGStore.upsert",
        return_value=None,
    ):
        response = client.post("/api/v1/charges/generate", json=payload)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["charge_draft"]["charge_lines"][0]["units"] == 1
    assert any(f["rule_type"] == "mue" and f["severity"] == "blocking" and "20610" in f["affected_codes"] for f in body["compliance_flags"])


def test_generate_charge_strips_ruled_out_diagnosis_link(client):
    """A ruled-out diagnosis is flagged blocking and stripped from any charge line linking to it."""
    payload = _load_fixture("negation_and_ruleout_trap.json")

    fake_responses = iter([
        {"normalized_notes": "Evaluated for possible appendicitis; CT ruled out appendicitis. Diagnosis: abdominal pain."},
        {"entities": [
            {"text": "appendicitis", "kind": "diagnosis", "status": "ruled_out", "laterality": None},
            {"text": "abdominal pain", "kind": "diagnosis", "status": "confirmed", "laterality": None},
            {"text": "emergency department visit, low to moderate complexity", "kind": "procedure", "laterality": None, "units": 1},
        ]},
        {
            "charge_lines": [
                {"code_system": "CPT", "code": "99283", "description": "ED visit, low to moderate complexity", "modifiers": [], "units": 1, "linked_diagnosis_codes": ["K35.80", "R10.9"]},
            ],
            "claim_notes": "Appendicitis was ruled out by imaging; coded on presenting symptom.",
        },
    ])

    rag_query = _rag_query_from_codes({
        "appendicitis": ("ICD-10-CM", "K35.80", "Unspecified acute appendicitis"),
        "abdominal pain": ("ICD-10-CM", "R10.9", "Unspecified abdominal pain"),
        "emergency department visit, low to moderate complexity": ("CPT", "99283", "ED visit, low to moderate complexity"),
    })

    with patch(
        "app.services.coding_service.CodingAIClient.analyze",
        side_effect=lambda _s, _u: next(fake_responses),
    ), patch(
        "app.services.coding_service.CodingRAGStore.query",
        side_effect=rag_query,
    ), patch(
        "app.services.coding_service.CodingRAGStore.upsert",
        return_value=None,
    ):
        response = client.post("/api/v1/charges/generate", json=payload)

    assert response.status_code == 200, response.text
    body = response.json()
    assert any(f["rule_type"] == "ruled_out_diagnosis" and f["severity"] == "blocking" for f in body["compliance_flags"])
    assert body["charge_draft"]["charge_lines"][0]["linked_diagnosis_codes"] == ["R10.9"]


def test_generate_charge_flags_medical_necessity_gap(client):
    """Lumbar MRI for uncomplicated low back pain is flagged but not removed (warning, not blocking)."""
    payload = _load_fixture("medical_necessity_gap.json")

    fake_responses = iter([
        {"normalized_notes": "Low back pain for 3 weeks, no red flags. MRI lumbar spine without contrast performed."},
        {"entities": [
            {"text": "low back pain", "kind": "diagnosis", "status": "confirmed", "laterality": None},
            {"text": "MRI lumbar spine without contrast", "kind": "procedure", "laterality": None, "units": 1},
        ]},
        {
            "charge_lines": [
                {"code_system": "CPT", "code": "72148", "description": "MRI lumbar spine without contrast", "modifiers": [], "units": 1, "linked_diagnosis_codes": ["M54.5"]},
            ],
            "claim_notes": "No red flags documented; necessity may not be met.",
        },
    ])

    rag_query = _rag_query_from_codes({
        "low back pain": ("ICD-10-CM", "M54.5", "Low back pain"),
        "mri lumbar spine without contrast": ("CPT", "72148", "MRI lumbar spine without contrast"),
    })

    with patch(
        "app.services.coding_service.CodingAIClient.analyze",
        side_effect=lambda _s, _u: next(fake_responses),
    ), patch(
        "app.services.coding_service.CodingRAGStore.query",
        side_effect=rag_query,
    ), patch(
        "app.services.coding_service.CodingRAGStore.upsert",
        return_value=None,
    ):
        response = client.post("/api/v1/charges/generate", json=payload)

    assert response.status_code == 200, response.text
    body = response.json()
    assert any(f["rule_type"] == "medical_necessity" and f["severity"] == "warning" and "72148" in f["affected_codes"] for f in body["compliance_flags"])
    assert len(body["charge_draft"]["charge_lines"]) == 1
