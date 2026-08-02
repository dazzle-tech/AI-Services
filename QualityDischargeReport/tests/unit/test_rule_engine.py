"""Unit tests for rule engine."""

from src.services.discharge_qa.rule_engine import RuleEngine


def test_completeness_from_quality_rules():
    engine = RuleEngine()
    content = {
        "patient_info": {"age": 65, "sex": "Male"},
        "encounter_summary": {"chief_complaint": "Chest pain"},
        "diagnoses": {"primary_diagnosis": "MI"},
        "medications": {"discharge_medications": [{"name": "Aspirin", "dose": "81mg", "frequency": "daily"}]},
        "disposition": {"discharge_disposition": "Home"},
    }
    quality_rules = {
        "completeness": {
            "required_fields": {
                "encounter_summary": ["hospital_course"],
            }
        }
    }

    findings = engine.evaluate(content, {}, [], quality_rules=quality_rules)

    assert any(item["field"] == "hospital_course" for item in findings["missing_items"])


def test_safety_flags_missing_return_precautions():
    engine = RuleEngine()
    content = {
        "diagnoses": {"primary_diagnosis": "Chest pain"},
        "medications": {"discharge_medications": [{"name": "Aspirin", "dose": "81mg", "frequency": "daily"}]},
        "allergies": {"allergies": ["No known drug allergies"]},
        "follow_up_and_instructions": {},
    }
    quality_rules = {
        "safety": {
            "warning_signs": {
                "require_return_precautions": {
                    "high_risk_conditions": ["chest pain"],
                    "severity": "high",
                }
            }
        }
    }

    findings = engine.evaluate(content, {}, [], quality_rules=quality_rules)

    assert any(error["location"]["field"] == "return_precautions" for error in findings["errors"])


def test_allergy_conflict_detected():
    engine = RuleEngine()
    content = {
        "medications": {"discharge_medications": [{"name": "Penicillin", "dose": "500mg", "frequency": "TID"}]},
        "allergies": {"allergies": ["Penicillin - causes rash"]},
    }
    quality_rules = {
        "safety": {"medication_checks": {"check_allergy_conflicts": True}},
        "consistency": {"check_medications": False, "check_diagnoses": False, "check_procedures": False},
    }

    findings = engine.evaluate(content, {"allergies": ["Penicillin"]}, [], quality_rules=quality_rules)

    assert any(error.get("severity") == "critical" for error in findings["errors"])


def test_report_medication_missing_from_discharge_list():
    engine = RuleEngine()
    content = {
        "medications": {
            "discharge_medications": [
                {"name": "Aspirin", "dose": "81mg", "frequency": "daily"},
                {"name": "Warfarin", "dose": "5mg", "frequency": "daily"},
            ]
        }
    }
    patient_record = {
        "medications": [
            {"name": "Aspirin", "dose": "81mg", "frequency": "daily"},
            {"name": "Clopidogrel", "dose": "75mg", "frequency": "daily"},
        ]
    }
    quality_rules = {"consistency": {"check_diagnoses": False, "check_procedures": False, "check_medications": True}}

    findings = engine.evaluate(content, patient_record, [], quality_rules=quality_rules)

    assert any("clopidogrel" in str(item).lower() for item in findings["inconsistencies"])
