"""Deterministic QA checks from templates and quality rules."""

import re
from typing import Any, Dict, List, Optional

from .conflict_resolver import ConflictResolver
from .normalizer import DischargeReportNormalizer

_med_field_normalizer = DischargeReportNormalizer()


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


def _normalize_sex(value: Any) -> str:
    normalized = _normalize_text(value)
    if normalized in {"m", "male"}:
        return "male"
    if normalized in {"f", "female"}:
        return "female"
    return normalized


def _patient_record_field(patient_record: Dict[str, Any], field: str) -> Any:
    """Return patient record values using common field aliases."""
    if field == "sex":
        return patient_record.get("sex") or patient_record.get("gender")
    return patient_record.get(field)


def _report_patient_field(patient_info: Dict[str, Any], field: str) -> Any:
    """Return report patient values using common field aliases."""
    if field == "sex":
        return patient_info.get("sex") or patient_info.get("gender")
    return patient_info.get(field)


def _allergy_term_variants(value: Any) -> List[str]:
    text = str(value).strip()
    if not text:
        return []
    variants = {_normalize_text(text)}
    short = _normalize_text(text.split("-")[0].split(",")[0])
    if short:
        variants.add(short)
    return [term for term in variants if term]


def _report_allergy_terms(content: Dict[str, Any]) -> set[str]:
    allergies_section = content.get("allergies", {})
    allergy_values: List[str] = []
    if isinstance(allergies_section, dict):
        allergy_values = allergies_section.get("allergies", []) or []
    elif isinstance(allergies_section, list):
        allergy_values = allergies_section
    terms: set[str] = set()
    for item in _med_field_normalizer.normalize_allergies(allergy_values):
        terms.update(_allergy_term_variants(item))
    return terms


def _record_allergy_terms(patient_record: Dict[str, Any]) -> set[str]:
    terms: set[str] = set()
    for item in _med_field_normalizer.normalize_allergies(patient_record.get("allergies", []) or []):
        terms.update(_allergy_term_variants(item))
    return terms


def _allergy_terms_match(left: str, right: str) -> bool:
    return bool(left and right and (left in right or right in left))


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


def _medications_by_name(content: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Map normalized medication name -> report med dict (discharge meds preferred)."""
    by_name: Dict[str, Dict[str, Any]] = {}
    meds = _get_section_content(content, "medications")
    for key in ("home_medications", "discharge_medications"):
        for med in meds.get(key, []) or []:
            if not isinstance(med, dict):
                continue
            name = med.get("name")
            if name:
                by_name[_normalize_text(name)] = med
    return by_name


def _patient_record_medications(patient_record: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return medications from the patient record, supporting common field aliases."""
    for key in ("medications", "medications_on_admission", "discharge_medications", "home_medications"):
        value = patient_record.get(key)
        if isinstance(value, list) and value:
            return [med for med in value if isinstance(med, dict)]
    return []


def _find_report_med(med_name: str, report_med_map: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Find a report medication by exact or partial name match."""
    if not med_name:
        return None
    direct = report_med_map.get(med_name)
    if direct:
        return direct
    for key, med in report_med_map.items():
        if med_name == key or med_name in key or key in med_name:
            return med
    return None


def _medication_in_report(med_name: str, report_meds: set[str], report_med_map: Dict[str, Dict[str, Any]]) -> bool:
    return med_name in report_meds or _find_report_med(med_name, report_med_map) is not None


def _normalize_scalar(value: Any) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        return _normalize_text(value)
    if isinstance(value, (int, float)):
        number = float(value)
        if number.is_integer():
            return str(int(number))
        return str(number)
    return _normalize_text(value)


def _patient_info_fields(check_dates: bool) -> List[str]:
    fields = ["age", "sex"]
    if check_dates:
        fields.extend(["admission_date", "discharge_date"])
    return fields


def _normalize_med_value(value: Any) -> str:
    return re.sub(r"\s+", "", _normalize_text(value))


def _report_med_field_value(report_med: Dict[str, Any], field: str) -> Any:
    """Return a medication field, inferring frequency from leftover name text when needed."""
    value = report_med.get(field)
    if value not in (None, ""):
        return value
    if field != "frequency":
        return value
    name = report_med.get("name", "")
    if isinstance(name, str) and name.strip():
        return _med_field_normalizer.extract_frequency(name)
    return value


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

        patient_info = _get_section_content(content, "patient_info")
        if patient_info or patient_record:
            check_dates = consistency_rules.get("check_dates", True)
            for field in _patient_info_fields(check_dates):
                report_value = _report_patient_field(patient_info, field)
                record_value = _patient_record_field(patient_record, field)
                if report_value in (None, "") or record_value in (None, ""):
                    continue
                report_normalized = (
                    _normalize_scalar(report_value)
                    if field != "sex"
                    else _normalize_sex(report_value)
                )
                record_normalized = (
                    _normalize_scalar(record_value)
                    if field != "sex"
                    else _normalize_sex(record_value)
                )
                if report_normalized != record_normalized:
                    inconsistencies.append(
                        {
                            "id": "",
                            "severity": "high" if field in {"age", "sex"} else "medium",
                            "section": "patient_info",
                            "field": field,
                            "report_value": report_value,
                            "source_value": record_value,
                            "source": "patient_record",
                            "ref_id": "",
                            "recommendation": (
                                f"Align patient {field} in the discharge report "
                                f"({report_value}) with the patient record ({record_value})"
                            ),
                        }
                    )

        if consistency_rules.get("check_allergies", True):
            report_allergies = _report_allergy_terms(content)
            record_allergies = _record_allergy_terms(patient_record)
            if report_allergies and record_allergies:
                for record_term in sorted(record_allergies):
                    if any(_allergy_terms_match(record_term, report_term) for report_term in report_allergies):
                        continue
                    inconsistencies.append(
                        {
                            "id": "",
                            "severity": "high",
                            "section": "allergies",
                            "field": "allergies",
                            "report_value": sorted(report_allergies),
                            "source_value": record_term,
                            "source": "patient_record",
                            "ref_id": record_term,
                            "recommendation": (
                                f"Document allergy '{record_term}' in the discharge report "
                                f"or reconcile with the patient record"
                            ),
                        }
                    )
                for report_term in sorted(report_allergies):
                    if any(_allergy_terms_match(report_term, record_term) for record_term in record_allergies):
                        continue
                    inconsistencies.append(
                        {
                            "id": "",
                            "severity": "medium",
                            "section": "allergies",
                            "field": "allergies",
                            "report_value": report_term,
                            "source_value": sorted(record_allergies),
                            "source": "patient_record",
                            "ref_id": report_term,
                            "recommendation": (
                                f"Confirm allergy '{report_term}' in the discharge report "
                                f"against the patient record"
                            ),
                        }
                    )

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
            report_med_map = _medications_by_name(content)

            for med in _patient_record_medications(patient_record):
                med_name = _normalize_text(med.get("name", ""))
                if not med_name:
                    continue
                if not _medication_in_report(med_name, report_meds, report_med_map):
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
                    continue

                report_med = _find_report_med(med_name, report_med_map)
                if not report_med:
                    continue

                for field in ("dose", "frequency"):
                    record_value = _normalize_med_value(med.get(field))
                    report_field_value = _report_med_field_value(report_med, field)
                    report_value = _normalize_med_value(report_field_value)
                    if record_value and report_value and record_value != report_value:
                        inconsistencies.append(
                            {
                                "id": "",
                                "severity": "high",
                                "section": "medications",
                                "field": field,
                                "report_value": report_field_value or "",
                                "source_value": med.get(field, ""),
                                "source": "patient_record",
                                "ref_id": med.get("name", ""),
                                "recommendation": (
                                    f"Align {med.get('name')} {field} in the discharge report "
                                    f"({report_field_value}) with the patient record ({med.get(field)})"
                                ),
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
            allergy_terms = list(_report_allergy_terms(content) | _record_allergy_terms(patient_record))
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
