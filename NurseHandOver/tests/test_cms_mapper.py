"""Tests for the CMS patient_data generate payload."""

import pytest
from pydantic import ValidationError

from app.services.chart_assembler import assemble_current_status
from app.services.cms_mapper import parse_generate_payload
from app.services.prompt_builder import build_user_prompt

CMS_PAYLOAD = {
    "handover_nurse": "Sarah Mitchell",
    "patient_data": {
        "allergies": [
            {"allergy_description": "Penicillin", "allergy_type_description": "Drug"},
            {"allergy_description": "Peanuts", "allergy_type_description": "Food"},
            {
                "allergy_description": "Resolved latex",
                "allergy_type_description": "Other",
                "status": "resolved",
            },
        ],
        "warnings": [
            {"virus_description": "MRSA colonisation", "type": "Infection Control"},
            {"virus_description": "Hepatitis B carrier", "type": "Blood-borne"},
        ],
        "last_hospital_course": "Admitted 28/08 via ED with community-acquired pneumonia.",
        "past_medical_history": [
            {
                "record_type": "Allergy",
                "record_description": "Description: Acetone, Start Date: 28/04/2026",
            },
            {
                "record_type": "Blood Transfusion",
                "record_description": "Blood Transfusion: Yes, When: 16/05/2025, Where: Hand",
            },
        ],
        "diagnosis": [
            {
                "diagnosis_type": "Principal",
                "diagnosis_code": "J18.9",
                "diagnosis_description": "Pneumonia, unspecified organism",
            },
            {
                "diagnosis_type": "Secondary",
                "diagnosis_code": "I48.0",
                "diagnosis_description": "Paroxysmal atrial fibrillation",
            },
        ],
        "vital_signs": {
            "respiratory_rate": "18",
            "bp_diastolic": "76",
            "bp_systolic": "128",
            "pain_score": "3",
            "pulse_rate": "88",
            "spo2_pct": "95",
            "temperature_c": "37.4",
        },
        "pending_operations": [
            {"operation_name": "Bronchoscopy", "requested_date": "2026-09-04T09:00:00"},
            {"operation_name": "PICC line insertion", "requested_date": "2026-09-03T14:30:00"},
        ],
    },
}


def test_parses_cms_payload_into_patient_chart():
    request = parse_generate_payload(CMS_PAYLOAD)
    assert request.handover_nurse == "Sarah Mitchell"
    patient = request.patient
    assert patient.patient_id == "unspecified"
    assert "Principal: Pneumonia, unspecified organism (J18.9)" in patient.diagnosis
    assert "Blood Transfusion:" in patient.past_medical_history
    assert "community-acquired pneumonia" in patient.hospital_course
    assert [a.name for a in patient.allergies][:2] == ["Penicillin", "Peanuts"]
    assert patient.warnings[0].text == "MRSA colonisation"
    assert {p.name for p in patient.pending_procedures} == {"Bronchoscopy", "PICC line insertion"}


def test_cms_vitals_are_latest_snapshot_and_bp_combined():
    request = parse_generate_payload(CMS_PAYLOAD)
    status = assemble_current_status(request.patient)
    by_type = {v.type: v for v in status.vital_signs}
    assert by_type["hr"].value == "88"
    assert by_type["bp"].value == "128/76"
    assert by_type["temp"].value == "37.4"
    assert by_type["rr"].value == "18"
    assert by_type["spo2"].value == "95"
    assert by_type["pain"].value == "3"


def test_cms_vital_history_keeps_last_per_type():
    payload = {
        "handover_nurse": "Sarah Mitchell",
        "patient_data": {
            "vital_signs": {
                "pulse_rate": [
                    {"value": "70", "recorded_at": "2026-09-01T08:00:00"},
                    {"value": "110", "recorded_at": "2026-09-02T14:00:00"},
                ],
                "spo2_pct": "95",
            }
        },
    }
    request = parse_generate_payload(payload)
    status = assemble_current_status(request.patient)
    by_type = {v.type: str(v.value) for v in status.vital_signs}
    assert by_type["hr"] == "110"
    assert by_type["spo2"] == "95"


def test_cms_drops_resolved_allergies():
    request = parse_generate_payload(CMS_PAYLOAD)
    status = assemble_current_status(request.patient)
    assert [a.name for a in status.allergies] == ["Penicillin", "Peanuts"]


def test_cms_prompt_contains_mapped_fields():
    request = parse_generate_payload(CMS_PAYLOAD)
    prompt = build_user_prompt(request.patient)
    assert "Penicillin" in prompt
    assert "MRSA colonisation" in prompt
    assert "Bronchoscopy" in prompt
    assert "J18.9" in prompt
    assert "128/76" in prompt
    assert "Resolved latex" not in prompt


def test_rejects_more_than_one_patient():
    with pytest.raises(ValidationError, match="Exactly one patient"):
        parse_generate_payload(
            {
                "shift_id": "shift-x",
                "nurse_id": "nurse_001",
                "patients": [
                    {"patient_id": "pt_a", "name": "A"},
                    {"patient_id": "pt_b", "name": "B"},
                ],
            }
        )
