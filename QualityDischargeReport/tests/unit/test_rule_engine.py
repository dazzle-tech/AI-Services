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


def test_medication_dose_mismatch_detected():
    engine = RuleEngine()
    content = {
        "medications": {
            "discharge_medications": [
                {"name": "Aspirin", "dose": "1mg", "frequency": "daily"},
                {"name": "Clopidogrel", "dose": "75mg", "frequency": "daily"},
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

    dose_mismatches = [
        item
        for item in findings["inconsistencies"]
        if item.get("field") == "dose" and "aspirin" in str(item.get("ref_id", "")).lower()
    ]
    assert len(dose_mismatches) == 1
    assert dose_mismatches[0]["report_value"] == "1mg"
    assert dose_mismatches[0]["source_value"] == "81mg"


def test_medications_on_admission_alias_detects_dose_mismatch():
    engine = RuleEngine()
    content = {
        "medications": {
            "discharge_medications": [
                {"name": "active1", "dose": "3 Capsule", "frequency": "twice daily"},
                {"name": "active2", "dose": "1 Mg", "frequency": "every 4 hours"},
            ]
        }
    }
    patient_record = {
        "medications_on_admission": [
            {"name": "active1", "dose": "3 Capsule", "frequency": "Twice daily"},
            {"name": "active2", "dose": "5 Mg", "frequency": "Every 4 hours"},
        ]
    }
    quality_rules = {"consistency": {"check_diagnoses": False, "check_procedures": False, "check_medications": True}}

    findings = engine.evaluate(content, patient_record, [], quality_rules=quality_rules)

    dose_mismatches = [
        item
        for item in findings["inconsistencies"]
        if item.get("field") == "dose" and "active2" in str(item.get("ref_id", "")).lower()
    ]
    assert len(dose_mismatches) == 1
    assert dose_mismatches[0]["report_value"] == "1 Mg"
    assert dose_mismatches[0]["source_value"] == "5 Mg"


def test_weekly_vs_daily_frequency_mismatch_detected():
    engine = RuleEngine()
    content = {
        "medications": {
            "discharge_medications": [
                {"name": "active1", "dose": "3 Capsule", "frequency": "twice weekly"},
                {"name": "active2", "dose": "1 Mg", "frequency": "every 4 hours"},
            ]
        }
    }
    patient_record = {
        "medications_on_admission": [
            {"name": "active1", "dose": "3 Capsule", "frequency": "Twice daily"},
            {"name": "active2", "dose": "5 Mg", "frequency": "Every 4 hours"},
        ]
    }
    quality_rules = {"consistency": {"check_diagnoses": False, "check_procedures": False, "check_medications": True}}

    findings = engine.evaluate(content, patient_record, [], quality_rules=quality_rules)

    frequency_mismatches = [
        item
        for item in findings["inconsistencies"]
        if item.get("field") == "frequency" and "active1" in str(item.get("ref_id", "")).lower()
    ]
    assert len(frequency_mismatches) == 1
    assert frequency_mismatches[0]["report_value"] == "twice weekly"
    assert frequency_mismatches[0]["source_value"] == "Twice daily"


def test_patient_age_mismatch_detected():
    engine = RuleEngine()
    content = {
        "patient_info": {"age": 20, "sex": "Male", "admission_date": "2024-01-15", "discharge_date": "2024-01-18"},
    }
    patient_record = {
        "age": 65,
        "sex": "Male",
        "admission_date": "2024-01-15",
        "discharge_date": "2024-01-18",
    }
    quality_rules = {
        "consistency": {
            "check_diagnoses": False,
            "check_medications": False,
            "check_procedures": False,
            "check_dates": True,
        }
    }

    findings = engine.evaluate(content, patient_record, [], quality_rules=quality_rules)

    age_mismatches = [
        item for item in findings["inconsistencies"] if item.get("field") == "age" and item.get("section") == "patient_info"
    ]
    assert len(age_mismatches) == 1
    assert age_mismatches[0]["report_value"] == 20
    assert age_mismatches[0]["source_value"] == 65
    assert age_mismatches[0]["severity"] == "high"
