import pytest

from models.schemas import AllergyDrugValidationRequest
from services.allergy_drug_rules import filter_llm_findings_to_request, merge_validation_response, run_deterministic_checks
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
    request = AllergyDrugValidationRequest(
        allergies=[{"allergy_description": "Clarithromycin", "allergy_type_description": "Drug"}],
        drugs=[{"drug_name": "Clarithromycin"}, {"drug_name": "Simvastatin"}, {"drug_name": "Rosuvastatin"}],
    )
    merged = merge_validation_response(response, [], request)
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
    request = AllergyDrugValidationRequest(
        allergies=[{"allergy_description": "Clarithromycin"}],
        drugs=[{"drug_name": "Simvastatin", "drug_name1": "Rosuvastatin"}],
    )
    deterministic = run_deterministic_checks(request)
    merged = merge_validation_response(response, deterministic, request)
    assert merged.quick_summary.overall_status == "CAUTION"
    assert any("Duplicate statin therapy" in finding.issue for finding in merged.detailed_validations)


def test_hallucinated_drug_findings_are_removed():
    request = AllergyDrugValidationRequest(
        allergies=[{"allergy_description": "Clarithromycin", "allergy_type_description": "Drug"}],
        drugs=[{"drug_name": "Clarithromycin"}, {"drug_name": "Simvastatin"}, {"drug_name": "Rosuvastatin"}],
    )
    response = ValidationResponse(
        quick_summary=QuickSummary(
            overall_status="CAUTION",
            top_priority="Multiple issues found",
        ),
        detailed_validations=[
            DetailedValidation(
                item="Clarithromycin",
                severity="critical",
                issue="Patient has a documented allergy to clarithromycin.",
                recommendation="Avoid prescribing clarithromycin.",
                evidence="Direct allergy match with documented patient allergy.",
            ),
            DetailedValidation(
                item="Colchicine and Simvastatin",
                severity="moderate",
                issue="Potential for increased risk of myopathy when colchicine is used with simvastatin.",
                recommendation="Monitor for muscle pain.",
                evidence="Colchicine was not in the request.",
            ),
            DetailedValidation(
                item="Colchicine",
                severity="info",
                issue="No direct allergy or drug interaction conflicts found.",
                recommendation="Proceed with prescribing if clinically indicated.",
                evidence="No known cross-reactivity with clarithromycin allergy.",
            ),
        ],
        recommended_alternatives=[],
        confidence_score=0.95,
    )
    filtered = filter_llm_findings_to_request(response, request)
    items = [finding.item for finding in filtered.detailed_validations]
    assert items == ["Clarithromycin"]
    assert all("Colchicine" not in finding.item for finding in filtered.detailed_validations)
