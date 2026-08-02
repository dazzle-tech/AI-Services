"""Unit tests for merge helpers."""

from src.services.discharge_qa.merge_utils import (
    merge_findings,
    merge_medications,
    normalize_content_sections,
    filter_resolved_findings,
)
from src.services.discharge_qa.rule_engine import RuleEngine


def test_merge_medications_preserves_ai_fields():
    normalized = [{"name": "Aspirin", "dose": "81mg", "frequency": "daily", "route": "PO"}]
    ai = [{"name": "Aspirin", "dose": "81mg", "frequency": "daily", "route": "PO", "duration": "ongoing", "instructions": "Take daily"}]

    merged = merge_medications(normalized, ai)

    assert merged[0]["duration"] == "ongoing"
    assert merged[0]["instructions"] == "Take daily"


def test_normalize_content_sections_handles_list_procedures():
    content = {
        "procedures_and_tests": [
            "Cardiac catheterization",
            "Percutaneous coronary intervention",
        ]
    }

    normalized = normalize_content_sections(content)

    assert normalized["procedures_and_tests"] == {
        "procedures": [
            "Cardiac catheterization",
            "Percutaneous coronary intervention",
        ]
    }


def test_rule_engine_recognizes_list_procedures():
    engine = RuleEngine()
    content = {
        "procedures_and_tests": [
            "Cardiac catheterization",
            "Percutaneous coronary intervention with stent placement",
        ]
    }
    patient_record = {
        "procedures": [
            "Cardiac catheterization",
            "Percutaneous coronary intervention",
        ]
    }
    quality_rules = {
        "consistency": {
            "check_diagnoses": False,
            "check_medications": False,
            "check_procedures": True,
        }
    }

    findings = engine.evaluate(content, patient_record, [], quality_rules=quality_rules)

    assert findings["inconsistencies"] == []


def test_merge_findings_adds_rule_engine_items():
    ai_result = {
        "errors": [],
        "missing_items": [],
        "inconsistencies": [],
        "recommended_corrections": [],
    }
    rule_findings = {
        "errors": [],
        "missing_items": [
            {
                "section": "encounter_summary",
                "field": "hospital_course",
                "required_by": "quality_rule",
                "why_required": "Required",
                "recommendation": "Add hospital course",
            }
        ],
        "inconsistencies": [],
        "recommended_corrections": [],
    }

    merged = merge_findings(ai_result, rule_findings)

    assert len(merged["missing_items"]) == 1
    assert len(merged["recommended_corrections"]) == 1


def test_filter_resolved_findings_removes_present_return_precautions():
    content = {
        "follow_up_and_instructions": {
            "return_precautions": [
                "Return to ED if chest pain, shortness of breath, or other concerning symptoms"
            ],
            "follow_up_appointments": ["Cardiology follow-up in 2 weeks"],
        }
    }
    qa_result = {
        "errors": [
            {
                "type": "missing_item",
                "section": "follow_up_and_instructions",
                "field": "return_precautions",
                "reason": "Required for high-risk cases",
            }
        ],
        "missing_items": [
            {
                "section": "follow_up_and_instructions",
                "field": "return_precautions",
            }
        ],
        "inconsistencies": [],
        "recommended_corrections": [
            {
                "action": "add",
                "section": "follow_up_and_instructions",
                "field": "return_precautions",
                "suggested_text": "",
                "rationale": "",
            },
            {
                "action": "add",
                "section": "",
                "field": "",
                "suggested_text": "",
                "rationale": "",
            },
        ],
    }

    filtered = filter_resolved_findings(qa_result, content)

    assert filtered["errors"] == []
    assert filtered["missing_items"] == []
    assert filtered["recommended_corrections"] == []
