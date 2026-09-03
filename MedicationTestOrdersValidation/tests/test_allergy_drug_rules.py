import pytest

from models.schemas import AllergyDrugValidationRequest
from services.allergy_drug_rules import merge_validation_response, run_deterministic_checks
from models.schemas import DetailedValidation, QuickSummary, ValidationResponse


def test_expand_drug_name1_fields():
    request = AllergyDrugValidationRequest(
        allergies=[],
        drugs=[{"drug_name": "Simvastatin", "drug_name1": "Rosuvastatin"}],
    )
    assert [drug.drug_name for drug in request.drugs] == ["Simvastatin", "Rosuvastatin"]


def test_clarithromycin_allergy_flags_clarithromycin_drug():
    request = AllergyDrugValidationRequest(
        allergies=[{"allergy_description": "Clarithromycin", "allergy_type_description": "Drug"}],
        drugs=[{"drug_name": "Clarithromycin"}],
    )
    findings = run_deterministic_checks(request)
    assert any("Direct allergy conflict" in finding.issue for finding in findings)


def test_duplicate_statins_flagged():
    request = AllergyDrugValidationRequest(
        allergies=[{"allergy_description": "Clarithromycin", "allergy_type_description": "Drug"}],
        drugs=[{"drug_name": "Simvastatin", "drug_name1": "Rosuvastatin"}],
    )
    findings = run_deterministic_checks(request)
    assert any("Duplicate statin therapy" in finding.issue for finding in findings)


def test_clarithromycin_allergy_with_statins_is_not_allergy_conflict():
    request = AllergyDrugValidationRequest(
        allergies=[{"allergy_description": "Clarithromycin", "allergy_type_description": "Drug"}],
        drugs=[{"drug_name": "Simvastatin", "drug_name1": "Rosuvastatin"}],
    )
    findings = run_deterministic_checks(request)
    assert not any("Direct allergy conflict" in finding.issue for finding in findings)


def test_merge_upgrades_safe_llm_response_when_llm_lists_critical_finding():
    response = ValidationResponse(
        quick_summary=QuickSummary(
            overall_status="SAFE",
            top_priority="No allergy or drug interaction conflicts found",
        ),
        detailed_validations=[
            DetailedValidation(
                item="Clarithromycin",
                severity="CRITICAL",
                issue="Patient has a documented allergy to clarithromycin.",
                recommendation="Avoid prescribing clarithromycin.",
                evidence="Direct allergy match with documented patient allergy.",
            ),
            DetailedValidation(
                item="Rosuvastatin and Simvastatin",
                severity="MODERATE",
                issue="Potential for duplicate therapy as both are statins.",
                recommendation="Evaluate the need for both statins; consider using one.",
                evidence="Both drugs belong to the statin class.",
            ),
        ],
        recommended_alternatives=[],
        confidence_score=0.95,
    )
    merged = merge_validation_response(response, [])
    assert merged.quick_summary.overall_status == "CONTRAINDICATED"
    assert merged.detailed_validations[0].severity == "critical"
    assert not any(finding.severity == "info" for finding in merged.detailed_validations)


def test_merge_upgrades_safe_llm_response():
    response = ValidationResponse(
        quick_summary=QuickSummary(
            overall_status="SAFE",
            top_priority="No allergy or drug interaction conflicts found",
        ),
        detailed_validations=[
            DetailedValidation(
                item="Simvastatin",
                severity="info",
                issue="No direct allergy match or drug-drug interaction identified",
                recommendation="Proceed with prescribed therapy",
                evidence="LLM response",
            )
        ],
        recommended_alternatives=[],
        confidence_score=0.95,
    )
    deterministic = run_deterministic_checks(
        AllergyDrugValidationRequest(
            allergies=[{"allergy_description": "Clarithromycin"}],
            drugs=[{"drug_name": "Simvastatin", "drug_name1": "Rosuvastatin"}],
        )
    )
    merged = merge_validation_response(response, deterministic)
    assert merged.quick_summary.overall_status == "CAUTION"
    assert any("Duplicate statin therapy" in finding.issue for finding in merged.detailed_validations)
