"""Deterministic QA checks from templates and quality rules."""

from typing import Any, Dict, List, Optional

from .conflict_resolver import ConflictResolver


def _field_present(section_content: Any, field: str) -> bool:
    if not isinstance(section_content, dict):
        return False
    if field not in section_content:
        return False
    value = section_content[field]
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return len(value) > 0
    return True


def _get_section_content(content: Dict[str, Any], section: str) -> Dict[str, Any]:
    section_content = content.get(section, {})
    if isinstance(section_content, dict):
        return section_content
    return {}


def _get_procedures(content: Dict[str, Any]) -> List[str]:
    section = content.get("procedures_and_tests")
    if isinstance(section, list):
        return [str(item) for item in section if item]
    if isinstance(section, dict):
        return [str(item) for item in section.get("procedures", []) or [] if item]
    return []


def _normalize_text(value: Any) -> str:
    return str(value).strip().lower()


def _allergy_terms(allergy_values: List[str], patient_record: Dict[str, Any]) -> List[str]:
    terms: List[str] = []
    for item in allergy_values:
        if item:
            terms.append(_normalize_text(item))
            terms.append(_normalize_text(str(item).split("-")[0].split(",")[0]))
    for item in patient_record.get("allergies", []) or []:
        if item:
            terms.append(_normalize_text(item))
            terms.append(_normalize_text(str(item).split("-")[0].split(",")[0]))
    return [term for term in terms if term]


def _allergy_conflicts_with_med(allergy_terms: List[str], med_name: str) -> Optional[str]:
    med_norm = _normalize_text(med_name)
    for allergy in allergy_terms:
        if allergy and (allergy in med_norm or med_norm in allergy):
            return allergy
    return None


def _medication_names(content: Dict[str, Any]) -> List[str]:
    names: List[str] = []
    meds = _get_section_content(content, "medications")
    for key in ("discharge_medications", "home_medications"):
        for med in meds.get(key, []) or []:
            if isinstance(med, dict):
                name = med.get("name")
                if name:
                    names.append(_normalize_text(name))
            elif isinstance(med, str) and med.strip():
                names.append(_normalize_text(med))
    return names


def _diagnosis_values(content: Dict[str, Any]) -> List[str]:
    diagnoses = _get_section_content(content, "diagnoses")
    values: List[str] = []
    primary = diagnoses.get("primary_diagnosis")
    if primary:
        values.append(_normalize_text(primary))
    for item in diagnoses.get("secondary_diagnoses", []) or []:
        if item:
            values.append(_normalize_text(item))
    return values


class RuleEngine:
    """Runs programmatic completeness, consistency, and safety checks."""

    def __init__(self, conflict_resolver: Optional[ConflictResolver] = None):
        self.conflict_resolver = conflict_resolver or ConflictResolver()

    def evaluate(
        self,
        content: Dict[str, Any],
        patient_record: Dict[str, Any],
        onsite_docs: List[Dict[str, Any]],
        report_template: Optional[Dict[str, Any]] = None,
        quality_rules: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        quality_rules = quality_rules or {}
        return {
            "errors": self._check_safety(content, patient_record, quality_rules),
            "missing_items": self._check_completeness(content, report_template, quality_rules),
            "inconsistencies": self._check_consistency(content, patient_record, onsite_docs, quality_rules),
            "recommended_corrections": [],
        }

    def _check_completeness(
        self,
        content: Dict[str, Any],
        report_template: Optional[Dict[str, Any]],
        quality_rules: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        missing_items: List[Dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()

        def add_missing(section: str, field: str, required_by: str, why_required: str, recommendation: str):
            key = (section, field)
            if key in seen:
                return
            seen.add(key)
            missing_items.append(
                {
                    "id": "",
                    "required_by": required_by,
                    "section": section,
                    "field": field,
                    "why_required": why_required,
                    "recommendation": recommendation,
                }
            )

        if report_template:
            for section in report_template.get("sections", []):
                if not section.get("required"):
                    continue
                section_name = section.get("name", "")
                section_content = _get_section_content(content, section_name)
                for field in section.get("fields", []):
                    if not _field_present(section_content, field):
                        add_missing(
                            section_name,
                            field,
                            "template",
                            f"Template requires {field} in {section_name}",
                            f"Add {field} to {section_name}",
                        )

        completeness = quality_rules.get("completeness", {})
        for section in completeness.get("required_sections", []):
            section_content = _get_section_content(content, section)
            if not section_content:
                add_missing(
                    section,
                    section,
                    "quality_rule",
                    f"Completeness rule requires section {section}",
                    f"Add the {section} section to the discharge report",
                )

        for section, fields in (completeness.get("required_fields") or {}).items():
            section_content = _get_section_content(content, section)
            for field in fields:
                if not _field_present(section_content, field):
                    add_missing(
                        section,
                        field,
                        "quality_rule",
                        f"Completeness rule requires {field} in {section}",
                        f"Add {field} to {section}",
                    )

        return missing_items

    def _check_consistency(
        self,
        content: Dict[str, Any],
        patient_record: Dict[str, Any],
        onsite_docs: List[Dict[str, Any]],
        quality_rules: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        consistency_rules = quality_rules.get("consistency", {})
        inconsistencies: List[Dict[str, Any]] = []

        if consistency_rules.get("check_diagnoses", True):
            report_diagnoses = set(_diagnosis_values(content))
            record_diagnoses = {_normalize_text(d) for d in patient_record.get("diagnoses", []) if d}

            for diagnosis in record_diagnoses:
                if diagnosis and not any(diagnosis in report_dx or report_dx in diagnosis for report_dx in report_diagnoses):
                    inconsistencies.append(
                        {
                            "id": "",
                            "severity": "high",
                            "section": "diagnoses",
                            "field": "primary_diagnosis",
                            "report_value": list(report_diagnoses),
                            "source_value": diagnosis,
                            "source": "patient_record",
                            "ref_id": "",
                            "recommendation": f"Add missing diagnosis '{diagnosis}' to the discharge report",
                        }
                    )

            for doc in sorted(onsite_docs or [], key=lambda d: d.get("timestamp", ""), reverse=True):
                doc_content = doc.get("content", "")
                if not isinstance(doc_content, str):
                    continue
                doc_text = doc_content.lower()
                for diagnosis in record_diagnoses:
                    if diagnosis and diagnosis not in " ".join(report_diagnoses) and diagnosis in doc_text:
                        inconsistencies.append(
                            {
                                "id": "",
                                "severity": "high",
                                "section": "diagnoses",
                                "field": "primary_diagnosis",
                                "report_value": list(report_diagnoses),
                                "source_value": diagnosis,
                                "source": "onsite_doc",
                                "ref_id": doc.get("doc_id", ""),
                                "recommendation": f"Align report diagnosis with onsite document {doc.get('doc_id', '')}",
                            }
                        )
                        break

        if consistency_rules.get("check_medications", True):
            report_meds = set(_medication_names(content))
            record_meds = {
                _normalize_text(med.get("name", ""))
                for med in patient_record.get("medications", []) or []
                if isinstance(med, dict) and med.get("name")
            }

            for med in patient_record.get("medications", []) or []:
                if not isinstance(med, dict):
                    continue
                med_name = _normalize_text(med.get("name", ""))
                if med_name and med_name not in report_meds:
                    inconsistencies.append(
                        {
                            "id": "",
                            "severity": "medium",
                            "section": "medications",
                            "field": "discharge_medications",
                            "report_value": list(report_meds),
                            "source_value": med,
                            "source": "patient_record",
                            "ref_id": "",
                            "recommendation": f"Confirm whether '{med.get('name')}' should appear on discharge medications",
                        }
                    )

        if consistency_rules.get("check_procedures", True):
            report_procedures = {_normalize_text(item) for item in _get_procedures(content)}
            for procedure in patient_record.get("procedures", []) or []:
                proc_name = _normalize_text(procedure)
                if proc_name and not any(proc_name in existing or existing in proc_name for existing in report_procedures):
                    inconsistencies.append(
                        {
                            "id": "",
                            "severity": "medium",
                            "section": "procedures_and_tests",
                            "field": "procedures",
                            "report_value": list(report_procedures),
                            "source_value": procedure,
                            "source": "patient_record",
                            "ref_id": "",
                            "recommendation": f"Document procedure '{procedure}' in the discharge report",
                        }
                    )

        return inconsistencies

    def _check_safety(
        self,
        content: Dict[str, Any],
        patient_record: Dict[str, Any],
        quality_rules: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        safety_rules = quality_rules.get("safety", {})
        medication_rules = safety_rules.get("medication_checks", {})
        errors: List[Dict[str, Any]] = []

        meds = _get_section_content(content, "medications").get("discharge_medications", []) or []
        for med in meds:
            if not isinstance(med, dict):
                continue
            name = med.get("name", "")
            if medication_rules.get("require_dose", True) and not med.get("dose"):
                errors.append(
                    {
                        "id": "",
                        "category": "safety",
                        "severity": "high",
                        "location": {"section": "medications", "field": "dose", "evidence_snippet": name},
                        "issue": f"Discharge medication '{name}' is missing a dose",
                        "expected": "Explicit dose for each discharge medication",
                        "observed": med,
                        "recommendation": f"Add dose information for {name}",
                        "references": [{"source": "quality_rule", "ref_id": "medication_checks.require_dose", "note": ""}],
                    }
                )
            if medication_rules.get("require_frequency", True) and not med.get("frequency"):
                errors.append(
                    {
                        "id": "",
                        "category": "safety",
                        "severity": "high",
                        "location": {"section": "medications", "field": "frequency", "evidence_snippet": name},
                        "issue": f"Discharge medication '{name}' is missing a frequency",
                        "expected": "Explicit frequency for each discharge medication",
                        "observed": med,
                        "recommendation": f"Add frequency information for {name}",
                        "references": [{"source": "quality_rule", "ref_id": "medication_checks.require_frequency", "note": ""}],
                    }
                )

        allergies_section = content.get("allergies", {})
        allergy_values: List[str] = []
        if isinstance(allergies_section, dict):
            allergy_values = allergies_section.get("allergies", []) or []
        elif isinstance(allergies_section, list):
            allergy_values = allergies_section

        allergy_rules = safety_rules.get("allergy_checks", {})
        if allergy_rules.get("require_allergy_section", True) and not allergy_values:
            errors.append(
                {
                    "id": "",
                    "category": "safety",
                    "severity": "medium",
                    "location": {"section": "allergies", "field": "allergies", "evidence_snippet": ""},
                    "issue": "Allergy section is missing or empty",
                    "expected": "Documented allergies or explicit NKDA statement",
                    "observed": allergy_values,
                    "recommendation": "Document allergies or state 'No known drug allergies'",
                    "references": [{"source": "quality_rule", "ref_id": "allergy_checks.require_allergy_section", "note": ""}],
                }
            )

        warning_rules = safety_rules.get("warning_signs", {})
        return_rules = warning_rules.get("require_return_precautions", {})
        high_risk_terms = return_rules.get("high_risk_conditions", []) if isinstance(return_rules, dict) else []
        report_text = " ".join(_diagnosis_values(content)).lower()
        follow_up = _get_section_content(content, "follow_up_and_instructions")
        return_precautions = follow_up.get("return_precautions", []) or []
        if high_risk_terms and any(term.lower() in report_text for term in high_risk_terms):
            if not return_precautions:
                errors.append(
                    {
                        "id": "",
                        "category": "safety",
                        "severity": return_rules.get("severity", "high"),
                        "location": {"section": "follow_up_and_instructions", "field": "return_precautions", "evidence_snippet": ""},
                        "issue": "High-risk case is missing return precautions",
                        "expected": "Return precautions for high-risk symptoms",
                        "observed": return_precautions,
                        "recommendation": "Add return precautions such as chest pain or shortness of breath",
                        "references": [{"source": "quality_rule", "ref_id": "warning_signs.require_return_precautions", "note": ""}],
                    }
                )

        if medication_rules.get("check_allergy_conflicts", True):
            allergy_terms = _allergy_terms(allergy_values, patient_record)
            for med in meds:
                if not isinstance(med, dict):
                    continue
                med_name = med.get("name", "")
                conflict = _allergy_conflicts_with_med(allergy_terms, med_name)
                if conflict:
                    errors.append(
                        {
                            "id": "",
                            "category": "safety",
                            "severity": "critical",
                            "location": {"section": "medications", "field": "discharge_medications", "evidence_snippet": med_name},
                            "issue": f"Potential allergy conflict: prescribed '{med_name}' with allergy '{conflict}'",
                            "expected": "No allergy conflicts in discharge medications",
                            "observed": {"medication": med, "allergy": conflict},
                            "recommendation": f"Review prescription of {med_name} against documented allergy",
                            "references": [{"source": "quality_rule", "ref_id": "medication_checks.check_allergy_conflicts", "note": ""}],
                        }
                    )

        return errors
