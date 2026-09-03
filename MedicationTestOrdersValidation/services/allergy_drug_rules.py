from config import Status
from models.drug_utils import normalize_drug_name
from models.schemas import AllergyDrugValidationRequest, DetailedValidation, ValidationResponse

_DRUG_CLASSES: dict[str, frozenset[str]] = {
    "macrolide": frozenset(
        {"clarithromycin", "azithromycin", "erythromycin", "telithromycin"}
    ),
    "statin": frozenset(
        {
            "simvastatin",
            "rosuvastatin",
            "atorvastatin",
            "pravastatin",
            "lovastatin",
            "fluvastatin",
            "pitavastatin",
        }
    ),
    "penicillin": frozenset(
        {
            "penicillin",
            "amoxicillin",
            "ampicillin",
            "piperacillin",
            "nafcillin",
            "oxacillin",
        }
    ),
}

_CYP3A4_INHIBITORS = frozenset({"clarithromycin", "erythromycin", "ketoconazole", "itraconazole"})


def drug_classes(name: str) -> set[str]:
    normalized = normalize_drug_name(name)
    return {label for label, members in _DRUG_CLASSES.items() if normalized in members}


def run_deterministic_checks(request: AllergyDrugValidationRequest) -> list[DetailedValidation]:
    findings: list[DetailedValidation] = []
    drugs = request.drugs

    for allergy in request.allergies:
        allergen = normalize_drug_name(allergy.allergy_description)
        if not allergen:
            continue
        allergen_classes = drug_classes(allergy.allergy_description)

        for drug in drugs:
            drug_name = drug.drug_name
            normalized_drug = normalize_drug_name(drug_name)
            if not normalized_drug:
                continue

            if normalized_drug == allergen:
                findings.append(
                    DetailedValidation(
                        item=drug_name,
                        severity="critical",
                        issue=f"Direct allergy conflict: patient is allergic to {allergy.allergy_description}",
                        recommendation="Do not administer this drug; choose a non-cross-reactive alternative",
                        evidence="Exact match between documented allergy and proposed drug",
                    )
                )
                continue

            shared_classes = allergen_classes & drug_classes(drug_name)
            if shared_classes:
                shared_label = ", ".join(sorted(shared_classes))
                findings.append(
                    DetailedValidation(
                        item=drug_name,
                        severity="high",
                        issue=(
                            f"Possible cross-reactivity: {drug_name} shares the {shared_label} "
                            f"class with documented allergy {allergy.allergy_description}"
                        ),
                        recommendation="Avoid unless benefit clearly outweighs risk; consider an alternative agent",
                        evidence="Same drug class as documented allergen",
                    )
                )

    statin_drugs = [drug.drug_name for drug in drugs if "statin" in drug_classes(drug.drug_name)]
    if len(statin_drugs) >= 2:
        findings.append(
            DetailedValidation(
                item=", ".join(statin_drugs),
                severity="moderate",
                issue="Duplicate statin therapy detected",
                recommendation="Avoid combining multiple statins; use a single statin at an appropriate dose",
                evidence="Two or more HMG-CoA reductase inhibitors listed together",
            )
        )

    inhibitor_drugs = [
        drug.drug_name
        for drug in drugs
        if normalize_drug_name(drug.drug_name) in _CYP3A4_INHIBITORS
    ]
    statin_list = [drug.drug_name for drug in drugs if "statin" in drug_classes(drug.drug_name)]
    if inhibitor_drugs and statin_list:
        findings.append(
            DetailedValidation(
                item=", ".join([*inhibitor_drugs, *statin_list]),
                severity="high",
                issue="Clinically significant drug-drug interaction: CYP3A4 inhibitor with statin therapy",
                recommendation=(
                    "Avoid the combination when possible, reduce statin dose, or choose a statin with lower "
                    "CYP3A4 interaction risk"
                ),
                evidence="Macrolide or azole CYP3A4 inhibition can raise statin exposure and myopathy risk",
            )
        )

    return findings


def merge_validation_response(
    response: ValidationResponse,
    deterministic_findings: list[DetailedValidation],
) -> ValidationResponse:
    merged_findings = _merge_findings(deterministic_findings, response.detailed_validations)
    merged_findings = _drop_contradictory_info_findings(merged_findings)
    overall_status = _overall_status_from_findings(merged_findings)
    top_priority = _top_priority_from_findings(merged_findings, overall_status)

    return ValidationResponse(
        quick_summary=response.quick_summary.model_copy(
            update={"overall_status": overall_status, "top_priority": top_priority}
        ),
        detailed_validations=merged_findings,
        recommended_alternatives=response.recommended_alternatives,
        confidence_score=max(
            response.confidence_score,
            0.98 if deterministic_findings else response.confidence_score,
        ),
        timestamp=response.timestamp,
    )


def normalize_severity(severity: str) -> str:
    return (severity or "info").strip().lower()


def _severity_rank(severity: str) -> int:
    return {
        "info": 0,
        "low": 1,
        "moderate": 2,
        "high": 3,
        "critical": 4,
    }.get(normalize_severity(severity), 0)


def _merge_findings(
    deterministic_findings: list[DetailedValidation],
    llm_findings: list[DetailedValidation],
) -> list[DetailedValidation]:
    merged_by_key: dict[tuple[str, str], DetailedValidation] = {}
    for finding in deterministic_findings + llm_findings:
        key = (finding.item.lower(), finding.issue.lower())
        existing = merged_by_key.get(key)
        if existing is None or _severity_rank(finding.severity) > _severity_rank(existing.severity):
            merged_by_key[key] = finding
    return list(merged_by_key.values())


def _drop_contradictory_info_findings(findings: list[DetailedValidation]) -> list[DetailedValidation]:
    if not any(_severity_rank(finding.severity) >= 2 for finding in findings):
        return findings
    return [finding for finding in findings if _severity_rank(finding.severity) > 0]


def _overall_status_from_findings(findings: list[DetailedValidation]) -> str:
    status = Status.SAFE
    for finding in findings:
        severity = normalize_severity(finding.severity)
        if severity == "critical":
            return Status.CONTRAINDICATED
        if severity in {"high", "moderate"}:
            status = Status.CAUTION
    return status


def _top_priority_from_findings(findings: list[DetailedValidation], overall_status: str) -> str:
    if overall_status == Status.SAFE:
        return "No allergy or drug interaction conflicts found"
    ranked = sorted(findings, key=lambda item: _severity_rank(item.severity), reverse=True)
    return ranked[0].issue if ranked else "Review validation findings"
