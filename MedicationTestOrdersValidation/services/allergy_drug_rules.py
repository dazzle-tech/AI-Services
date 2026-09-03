import re
from itertools import combinations

from config import Status
from models.drug_utils import normalize_drug_name
from models.schemas import AllergyDrugValidationRequest, DetailedValidation, RecommendedAlternative, ValidationResponse

_ITEM_SPLIT_RE = re.compile(r"\s*(?:,| and | with | \+ )\s*", re.IGNORECASE)

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
    "cephalosporin": frozenset(
        {
            "cefazolin",
            "cephalexin",
            "ceftriaxone",
            "cefuroxime",
            "cefepime",
            "ceftazidime",
        }
    ),
    "sulfa": frozenset(
        {
            "sulfamethoxazole",
            "trimethoprim",
            "sulfasalazine",
            "furosemide",
        }
    ),
    "fluoroquinolone": frozenset(
        {
            "ciprofloxacin",
            "levofloxacin",
            "moxifloxacin",
            "ofloxacin",
        }
    ),
}

# Indirect allergy risk between drug classes (allergen class -> drug class).
_CROSS_CLASS_ALLERGY_REACTIVITY: tuple[tuple[str, str, str, str], ...] = (
    (
        "penicillin",
        "cephalosporin",
        "high",
        "Indirect allergy risk: beta-lactam cross-reactivity between penicillins and cephalosporins",
    ),
    (
        "cephalosporin",
        "penicillin",
        "high",
        "Indirect allergy risk: beta-lactam cross-reactivity between cephalosporins and penicillins",
    ),
)

_ALLERGEN_CLASS_KEYWORDS: dict[str, str] = {
    "macrolide": "macrolide",
    "macrolides": "macrolide",
    "penicillin": "penicillin",
    "penicillins": "penicillin",
    "cephalosporin": "cephalosporin",
    "cephalosporins": "cephalosporin",
    "sulfa": "sulfa",
    "sulfonamide": "sulfa",
    "sulfonamides": "sulfa",
    "fluoroquinolone": "fluoroquinolone",
    "fluoroquinolones": "fluoroquinolone",
    "statin": "statin",
    "statins": "statin",
}

_CYP3A4_INHIBITORS = frozenset({"clarithromycin", "erythromycin", "ketoconazole", "itraconazole"})
_COLCHICINE = frozenset({"colchicine"})


def drug_classes(name: str) -> set[str]:
    normalized = normalize_drug_name(name)
    classes = {label for label, members in _DRUG_CLASSES.items() if normalized in members}
    for keyword, class_name in _ALLERGEN_CLASS_KEYWORDS.items():
        if keyword in normalized:
            classes.add(class_name)
    return classes


def allergen_classes(allergy_description: str) -> set[str]:
    return drug_classes(allergy_description)


def _is_statin(name: str) -> bool:
    return "statin" in drug_classes(name)


def _is_colchicine(name: str) -> bool:
    return normalize_drug_name(name) in _COLCHICINE


def _is_cyp3a4_inhibitor(name: str) -> bool:
    return normalize_drug_name(name) in _CYP3A4_INHIBITORS


def _append_unique_finding(findings: list[DetailedValidation], finding: DetailedValidation) -> None:
    key = (finding.item.lower(), finding.issue.lower())
    existing = {(item.item.lower(), item.issue.lower()): item for item in findings}
    current = existing.get(key)
    if current is None or _severity_rank(finding.severity) > _severity_rank(current.severity):
        if current is not None:
            findings.remove(current)
        findings.append(finding)


def _check_drug_against_allergy(
    drug_name: str,
    allergy_description: str,
) -> DetailedValidation | None:
    allergen = normalize_drug_name(allergy_description)
    normalized_drug = normalize_drug_name(drug_name)
    if not allergen or not normalized_drug:
        return None

    if normalized_drug == allergen:
        return DetailedValidation(
            item=drug_name,
            severity="critical",
            issue=f"Direct allergy conflict: patient is allergic to {allergy_description}",
            recommendation="Do not administer this drug; choose a non-cross-reactive alternative",
            evidence="Exact match between documented allergy and proposed drug",
        )

    allergen_class_set = allergen_classes(allergy_description)
    drug_class_set = drug_classes(drug_name)
    shared_classes = allergen_class_set & drug_class_set
    if shared_classes:
        shared_label = ", ".join(sorted(shared_classes))
        return DetailedValidation(
            item=drug_name,
            severity="high",
            issue=(
                f"Indirect allergy risk (same drug class): {drug_name} shares the {shared_label} "
                f"class with documented allergy {allergy_description}"
            ),
            recommendation="Avoid unless benefit clearly outweighs risk; consider a non-cross-reactive alternative",
            evidence="Cross-reactivity within the same drug class as the documented allergen",
        )

    for allergen_class, drug_class, severity, issue in _CROSS_CLASS_ALLERGY_REACTIVITY:
        if allergen_class in allergen_class_set and drug_class in drug_class_set:
            return DetailedValidation(
                item=drug_name,
                severity=severity,
                issue=f"{issue} for {drug_name} with documented allergy {allergy_description}",
                recommendation="Avoid unless benefit clearly outweighs risk; consider a non-cross-reactive alternative",
                evidence="Known cross-class beta-lactam allergy cross-reactivity",
            )

    return None


def _allergy_screening_finding(drug_name: str, allergy_description: str) -> DetailedValidation:
    return DetailedValidation(
        item=drug_name,
        severity="info",
        issue=(
            f"Allergy screening: no direct or cross-reactive allergy conflict with "
            f"{allergy_description} for {drug_name}"
        ),
        recommendation="No allergy-based change required for this drug based on documented allergies",
        evidence="Checked direct match, same-class cross-reactivity, and known cross-class allergy patterns",
    )


def run_deterministic_checks(request: AllergyDrugValidationRequest) -> list[DetailedValidation]:
    findings: list[DetailedValidation] = []
    drug_names = [drug.drug_name for drug in request.drugs]

    for allergy in request.allergies:
        if not normalize_drug_name(allergy.allergy_description):
            continue

        for drug_name in drug_names:
            if not normalize_drug_name(drug_name):
                continue

            allergy_finding = _check_drug_against_allergy(drug_name, allergy.allergy_description)
            if allergy_finding:
                _append_unique_finding(findings, allergy_finding)
            else:
                _append_unique_finding(
                    findings,
                    _allergy_screening_finding(drug_name, allergy.allergy_description),
                )

    statin_drugs = [name for name in drug_names if _is_statin(name)]
    if len(statin_drugs) >= 2:
        _append_unique_finding(
            findings,
            DetailedValidation(
                item=", ".join(statin_drugs),
                severity="moderate",
                issue="Duplicate statin therapy detected",
                recommendation="Avoid combining multiple statins; use a single statin at an appropriate dose",
                evidence="Two or more HMG-CoA reductase inhibitors listed together",
            ),
        )

    for left, right in combinations(drug_names, 2):
        pair_label = f"{left} and {right}"

        if (_is_colchicine(left) and _is_statin(right)) or (_is_colchicine(right) and _is_statin(left)):
            _append_unique_finding(
                findings,
                DetailedValidation(
                    item=pair_label,
                    severity="moderate",
                    issue="Drug-drug interaction: colchicine combined with statin therapy increases myopathy/rhabdomyolysis risk",
                    recommendation="Monitor closely for muscle pain or weakness; consider dose adjustment or alternative therapy",
                    evidence="Colchicine and statins both increase muscle-related adverse effect risk",
                ),
            )

        if (_is_cyp3a4_inhibitor(left) and _is_statin(right)) or (_is_cyp3a4_inhibitor(right) and _is_statin(left)):
            _append_unique_finding(
                findings,
                DetailedValidation(
                    item=pair_label,
                    severity="high",
                    issue="Drug-drug interaction: CYP3A4 inhibitor combined with statin therapy",
                    recommendation=(
                        "Avoid the combination when possible, reduce statin dose, or choose a statin with lower "
                        "CYP3A4 interaction risk"
                    ),
                    evidence="CYP3A4 inhibition can raise statin exposure and myopathy risk",
                ),
            )

    return findings


def drug_names_from_request(request: AllergyDrugValidationRequest) -> set[str]:
    names = {normalize_drug_name(drug.drug_name) for drug in request.drugs}
    names.discard("")
    return names


def _tokens_from_label(label: str) -> list[str]:
    return [part.strip() for part in _ITEM_SPLIT_RE.split(label or "") if part.strip()]


def finding_uses_only_allowed_drugs(
    finding: DetailedValidation,
    allowed_drugs: set[str],
) -> bool:
    if not allowed_drugs:
        return True
    tokens = _tokens_from_label(finding.item)
    if not tokens:
        return False
    return all(normalize_drug_name(token) in allowed_drugs for token in tokens)


def alternative_uses_only_allowed_drugs(
    alternative: RecommendedAlternative,
    allowed_drugs: set[str],
) -> bool:
    if not allowed_drugs:
        return True
    tokens = _tokens_from_label(alternative.original_item)
    if not tokens:
        return False
    return all(normalize_drug_name(token) in allowed_drugs for token in tokens)


def filter_llm_findings_to_request(
    response: ValidationResponse,
    request: AllergyDrugValidationRequest,
) -> ValidationResponse:
    allowed_drugs = drug_names_from_request(request)
    filtered_findings = [
        finding
        for finding in response.detailed_validations
        if finding_uses_only_allowed_drugs(finding, allowed_drugs)
    ]
    filtered_alternatives = [
        alternative
        for alternative in response.recommended_alternatives
        if alternative_uses_only_allowed_drugs(alternative, allowed_drugs)
    ]
    return response.model_copy(
        update={
            "detailed_validations": filtered_findings,
            "recommended_alternatives": filtered_alternatives,
        }
    )


def merge_validation_response(
    response: ValidationResponse,
    deterministic_findings: list[DetailedValidation],
    request: AllergyDrugValidationRequest,
) -> ValidationResponse:
    response = filter_llm_findings_to_request(response, request)
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
    return [
        finding
        for finding in findings
        if _severity_rank(finding.severity) > 0 or finding.issue.lower().startswith("allergy screening:")
    ]


def _overall_status_from_findings(findings: list[DetailedValidation]) -> str:
    status = Status.SAFE
    for finding in findings:
        severity = normalize_severity(finding.severity)
        if severity == "critical":
            return Status.CONTRAINDICATED
        if severity in {"high", "moderate"}:
            status = Status.CAUTION
    return status


_NO_ALLERGY_CONFLICTS = "No allergy conflicts found"
_NO_DRUG_INTERACTION_CONFLICTS = "No drug-drug interaction conflicts found"


def _finding_category(finding: DetailedValidation) -> str:
    issue = finding.issue.lower()
    if "allergy" in issue or "cross-reactiv" in issue:
        return "allergy"
    if "drug-drug interaction" in issue or "duplicate statin" in issue:
        return "ddi"
    return "other"


def _top_issue_for_category(findings: list[DetailedValidation], category: str) -> DetailedValidation | None:
    category_findings = [
        finding
        for finding in findings
        if _finding_category(finding) == category and _severity_rank(finding.severity) > 0
    ]
    if not category_findings:
        return None
    return sorted(category_findings, key=lambda item: _severity_rank(item.severity), reverse=True)[0]


def _allergy_summary_text(findings: list[DetailedValidation]) -> str:
    allergy_issue = _top_issue_for_category(findings, "allergy")
    if allergy_issue:
        return _summary_issue_text(allergy_issue, "allergy")

    screened = [
        finding
        for finding in findings
        if finding.issue.lower().startswith("allergy screening:")
    ]
    if screened:
        return "No direct or cross-reactive allergy conflicts found after screening all listed drugs"

    return _NO_ALLERGY_CONFLICTS


def _summary_issue_text(finding: DetailedValidation, category: str) -> str:
    issue = finding.issue.strip()
    if category == "ddi":
        lowered = issue.lower()
        for prefix in ("drug-drug interaction:", "drug interaction:"):
            if lowered.startswith(prefix):
                return issue[len(prefix) :].strip()
    if category == "allergy":
        lowered = issue.lower()
        for prefix in ("direct allergy conflict:", "allergy conflict:", "possible cross-reactivity:"):
            if lowered.startswith(prefix):
                return issue
    return issue


def _top_priority_from_findings(findings: list[DetailedValidation], overall_status: str) -> str:
    if overall_status == Status.SAFE:
        return "No allergy or drug-drug interaction conflicts found"

    allergy_issue = _top_issue_for_category(findings, "allergy")
    ddi_issue = _top_issue_for_category(findings, "ddi")

    parts: list[str] = []
    if allergy_issue:
        parts.append(f"Allergy: {_summary_issue_text(allergy_issue, 'allergy')}")
    else:
        parts.append(f"Allergy: {_allergy_summary_text(findings)}")

    if ddi_issue:
        parts.append(f"Drug-drug interaction: {_summary_issue_text(ddi_issue, 'ddi')}")
    else:
        parts.append(f"Drug-drug interaction: {_NO_DRUG_INTERACTION_CONFLICTS}")

    if allergy_issue or ddi_issue:
        return "; ".join(parts)

    ranked = sorted(findings, key=lambda item: _severity_rank(item.severity), reverse=True)
    return ranked[0].issue if ranked else "Review validation findings"
