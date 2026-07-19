"""Validation and safety checks for extracted data."""
from typing import Dict, Any, List, Optional, Tuple
from app.models.schemas import StructuredFields, UncertaintyFlag, ContradictionFlag, Warning

from datetime import datetime
import json
from pydantic import BaseModel


STRING_FIELDS = {
    "chief_complaint",
    "history_of_present_illness",
    "assessment",
    "plan",
    "past_medical_history",
    "family_history",
    "social_history",
}

LIST_STRING_FIELDS = {
    "diagnosis",
    "procedures",
}

LIST_DICT_FIELDS = {
    "medications",
}

DICT_FIELDS = {
    "vitals",
    "review_of_systems",
}


def _actual_type_name(value: Any) -> str:
    """Return a human-readable type description for validation messages."""
    if value is None:
        return "null"
    if isinstance(value, list):
        if not value:
            return "list[empty]"
        item_types = sorted({type(item).__name__ for item in value})
        return f"list[{', '.join(item_types)}]"
    if isinstance(value, dict):
        return "dict"
    return type(value).__name__


def _join_list_values(values: List[Any]) -> str:
    """Join list values into a comma-separated string."""
    items = []
    for item in values:
        if item is None:
            continue
        if isinstance(item, str):
            text = item.strip()
        else:
            text = str(item).strip()
        if text:
            items.append(text)
    return ", ".join(items)


def _normalize_allergy_list(value: Any) -> Optional[List[str]]:
    """Normalize allergy values and keep 'no known allergies' consistent as an empty list."""
    if value is None:
        return None

    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return []
        lowered = normalized.lower()
        if lowered in {"no known allergies", "nkda", "none", "no allergies"}:
            return []
        return [normalized]

    if isinstance(value, list):
        normalized = []
        for item in value:
            if item is None:
                continue
            text = item.strip() if isinstance(item, str) else str(item).strip()
            if not text:
                continue
            lowered = text.lower()
            if lowered in {"no known allergies", "nkda", "none", "no allergies"}:
                return []
            normalized.append(text)
        return normalized

    text = str(value).strip()
    if not text:
        return []
    lowered = text.lower()
    if lowered in {"no known allergies", "nkda", "none", "no allergies"}:
        return []
    return [text]


def normalize_history_of_present_illness(user_text: str, hpi: Optional[str]) -> Optional[str]:
    """Ensure HPI keeps demographic context when present in the source text."""
    if not hpi or not user_text:
        return hpi

    source = user_text.strip()
    normalized_hpi = hpi.strip()
    lower_source = source.lower()
    lower_hpi = normalized_hpi.lower()
    import re

    if re.search(r"\b\d{1,3}-year-old\s+(male|female)\b", lower_source):
        first_sentence = source.split(".", 1)[0].strip()
        if first_sentence:
            return first_sentence + ("." if source.endswith(".") and not first_sentence.endswith(".") else "")

    if lower_source.startswith(lower_hpi):
        return source[: len(hpi)].strip()

    if lower_hpi in lower_source:
        start = lower_source.find(lower_hpi)
        prefix = source[:start].strip(" ,:-")
        candidate = source[start : start + len(hpi)].strip()
        if prefix:
            result = f"{prefix} {candidate}".strip()
            if source.rstrip().endswith(".") and not result.endswith("."):
                result += "."
            return result

    if "presenting with" in lower_source and "presenting with" not in lower_hpi:
        prefix_idx = lower_source.find("presenting with")
        return source[prefix_idx:].strip()

    return hpi


def normalize_source_trace_source(
    field_name: str,
    source: str,
    user_text: str,
    structured_fields: Dict[str, Any],
    patient_data: Dict[str, Any]
) -> str:
    """Prefer user_text when the field is explicitly mentioned there."""
    if source == "user_text":
        return source

    text_lower = (user_text or "").lower()
    if field_name == "medications":
        meds = structured_fields.get("medications") or []
        for med in meds:
            if isinstance(med, dict):
                name = str(med.get("name", "")).strip().lower()
                dosage = str(med.get("dosage", "")).strip().lower()
                if name and name in text_lower:
                    return "user_text"
                if dosage and dosage in text_lower:
                    return "user_text"
        patient_meds = patient_data.get("medications") or []
        if meds and patient_meds:
            return "user_text"

    if field_name == "allergies":
        allergies = structured_fields.get("allergies") or []
        if not allergies:
            return "patient_record" if patient_data.get("allergies") is not None else "user_text"
        return "user_text" if any(a.lower() in text_lower for a in allergies if isinstance(a, str)) else source

    return source


def build_field_source_trace(
    field_name: str,
    user_text: str,
    patient_data: Dict[str, Any],
    structured_fields: Dict[str, Any],
    default_source: str = "user_text"
) -> Dict[str, Any]:
    """Build a trace record for a field using the most accurate source available."""
    source = normalize_source_trace_source(
        field_name=field_name,
        source=default_source,
        user_text=user_text,
        structured_fields=structured_fields,
        patient_data=patient_data
    )
    return {
        "field_name": field_name,
        "source": source,
        "extraction_method": "direct",
    }


def filter_completed_procedures(procedures: Any, user_text: str) -> Optional[List[str]]:
    """
    Keep only procedures that look completed/performed, not merely planned or ordered.
    """
    if procedures is None:
        return None

    if not isinstance(procedures, list):
        procedures = [procedures]

    user_text_lower = (user_text or "").lower()
    plan_markers = ("plan:", "plan -", "order", "ordered", "schedule", "scheduled", "will perform", "to be performed")
    completion_markers = ("performed", "completed", "done", "obtained", "revealed", "showed", "was done", "was performed")

    # If the note only mentions procedures in the plan section and nowhere
    # indicates they were completed, do not surface them as performed procedures.
    if any(marker in user_text_lower for marker in plan_markers) and not any(marker in user_text_lower for marker in completion_markers):
        return None

    filtered: List[str] = []
    for item in procedures:
        text = item.strip() if isinstance(item, str) else str(item).strip()
        if not text:
            continue

        occurrence = user_text_lower.find(text.lower())
        if occurrence >= 0:
            window_start = max(0, occurrence - 80)
            window_end = min(len(user_text_lower), occurrence + len(text) + 80)
            window = user_text_lower[window_start:window_end]
            if any(marker in window for marker in plan_markers) and not any(marker in window for marker in completion_markers):
                continue

        filtered.append(text)

    return filtered


def _normalize_string_field(field_name: str, value: Any) -> Tuple[Optional[str], Optional[Warning]]:
    """Normalize a field that should be serialized as a string."""
    expected = "string"
    actual = _actual_type_name(value)

    if value is None:
        return None, None

    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return None, Warning(
                level="warning",
                message=(
                    f"Field '{field_name}' expected {expected} but received empty string; "
                    "value was omitted"
                ),
                field_name=field_name
            )
        return normalized, None

    if isinstance(value, list):
        normalized = _join_list_values(value)
        if normalized:
            return normalized, Warning(
                level="warning",
                message=(
                    f"Field '{field_name}' expected {expected} but received {actual}; "
                    f"converted to comma-separated string"
                ),
                field_name=field_name
            )
        return None, Warning(
            level="warning",
            message=(
                f"Field '{field_name}' expected {expected} but received {actual}; "
                "value could not be converted"
            ),
            field_name=field_name
        )

    if isinstance(value, dict):
        try:
            normalized = json.dumps(value, ensure_ascii=False)
        except TypeError:
            normalized = str(value)
        return normalized, Warning(
            level="warning",
            message=(
                f"Field '{field_name}' expected {expected} but received {actual}; "
                f"converted to string"
            ),
            field_name=field_name
        )

    normalized = str(value).strip()
    if normalized:
        return normalized, Warning(
            level="warning",
            message=(
                f"Field '{field_name}' expected {expected} but received {actual}; "
                f"converted to string"
            ),
            field_name=field_name
        )

    return None, Warning(
        level="warning",
        message=(
            f"Field '{field_name}' expected {expected} but received {actual}; "
            "value could not be converted"
        ),
        field_name=field_name
    )


def _normalize_list_field(field_name: str, value: Any) -> Tuple[Optional[List[str]], Optional[Warning]]:
    """Normalize a field that should be serialized as a list of strings."""
    expected = "list[str]"
    actual = _actual_type_name(value)

    if value is None:
        return None, None

    if isinstance(value, list):
        normalized = []
        for item in value:
            if item is None:
                continue
            text = item.strip() if isinstance(item, str) else str(item).strip()
            if text:
                normalized.append(text)
        return normalized, None

    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return None, Warning(
                level="warning",
                message=(
                    f"Field '{field_name}' expected {expected} but received empty string; "
                    "value was omitted"
                ),
                field_name=field_name
            )
        if "," in normalized:
            items = [item.strip() for item in normalized.split(",") if item.strip()]
            return items, Warning(
                level="warning",
                message=(
                    f"Field '{field_name}' expected {expected} but received {actual}; "
                    "split comma-separated string into a list"
                ),
                field_name=field_name
            )
        return [normalized], Warning(
            level="warning",
            message=(
                f"Field '{field_name}' expected {expected} but received {actual}; "
                "wrapped string value in a list"
            ),
            field_name=field_name
        )

    return None, Warning(
        level="warning",
        message=(
            f"Field '{field_name}' expected {expected} but received {actual}; "
            "value could not be converted"
        ),
        field_name=field_name
    )


def _normalize_medication_field(field_name: str, value: Any) -> Tuple[Optional[List[Dict[str, Any]]], Optional[Warning]]:
    """Normalize medications into a list of dictionaries."""
    expected = "list[dict]"
    actual = _actual_type_name(value)

    if value is None:
        return None, None

    if isinstance(value, list):
        normalized = []
        for item in value:
            if item is None:
                continue
            if isinstance(item, dict):
                normalized.append(item)
            elif isinstance(item, str):
                text = item.strip()
                if text:
                    normalized.append({"name": text})
            else:
                text = str(item).strip()
                if text:
                    normalized.append({"name": text})
        return normalized, None

    if isinstance(value, dict):
        return [value], Warning(
            level="warning",
            message=(
                f"Field '{field_name}' expected {expected} but received {actual}; "
                "wrapped dictionary value in a list"
            ),
            field_name=field_name
        )

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None, Warning(
                level="warning",
                message=(
                    f"Field '{field_name}' expected {expected} but received empty string; "
                    "value was omitted"
                ),
                field_name=field_name
            )
        return [{"name": text}], Warning(
            level="warning",
            message=(
                f"Field '{field_name}' expected {expected} but received {actual}; "
                "wrapped string value in a medication object"
            ),
            field_name=field_name
        )

    return None, Warning(
        level="warning",
        message=(
            f"Field '{field_name}' expected {expected} but received {actual}; "
            "value could not be converted"
        ),
        field_name=field_name
    )


def _normalize_dict_field(field_name: str, value: Any) -> Tuple[Optional[Dict[str, Any]], Optional[Warning]]:
    """Normalize a field that should remain a dictionary."""
    expected = "dict"
    actual = _actual_type_name(value)

    if value is None:
        return None, None

    if isinstance(value, dict):
        return value, None

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None, Warning(
                level="warning",
                message=(
                    f"Field '{field_name}' expected {expected} but received empty string; "
                    "value was omitted"
                ),
                field_name=field_name
            )

        if field_name == "vitals":
            normalized_vitals = _normalize_vitals_string(text)
            return normalized_vitals, Warning(
                level="warning",
                message=(
                    f"Field '{field_name}' expected {expected} but received {actual}; "
                    "parsed string into vitals dictionary"
                ),
                field_name=field_name
            )

        return {"value": text}, Warning(
            level="warning",
            message=(
                f"Field '{field_name}' expected {expected} but received {actual}; "
                "wrapped string value in a dictionary"
            ),
            field_name=field_name
        )

    return None, Warning(
        level="warning",
        message=(
            f"Field '{field_name}' expected {expected} but received {actual}; "
            "value could not be converted"
        ),
        field_name=field_name
    )


def _normalize_vitals_string(value: str) -> Dict[str, Any]:
    """Best-effort parse a vitals string into a dictionary."""
    import re

    text = value.strip()
    vitals: Dict[str, Any] = {
        "bp": None,
        "hr": None,
        "temp": None,
        "o2_sat": None,
        "rr": None,
        "raw": text,
    }

    bp_match = re.search(r'(\d{2,3}/\d{2,3})', text)
    if bp_match:
        vitals["bp"] = bp_match.group(1)

    hr_match = re.search(r'(?:hr|heart\s+rate)\s*(?:is\s*)?(\d{2,3})\s*(?:bpm)?', text, re.IGNORECASE)
    if hr_match:
        vitals["hr"] = f"{hr_match.group(1)} bpm"

    temp_match = re.search(r'(\d{2,3}(?:\.\d+)?)\s*(?:c|°c|f|°f|temp(?:erature)?)', text, re.IGNORECASE)
    if temp_match:
        vitals["temp"] = temp_match.group(1)

    rr_match = re.search(r'(?:rr|respiratory\s+rate)\s*(?:is\s*)?(\d{1,2})', text, re.IGNORECASE)
    if rr_match:
        vitals["rr"] = rr_match.group(1)

    o2_match = re.search(r'(\d{2,3})\s*%?\s*(?:o2\s*sat|spo2|oxygen\s+saturation)', text, re.IGNORECASE)
    if o2_match:
        vitals["o2_sat"] = f"{o2_match.group(1)}%"

    return vitals


def build_structured_fields(
    structured_fields: Dict[str, Any]
) -> Tuple[StructuredFields, List[Warning]]:
    """
    Build a StructuredFields model while coercing field values independently.

    This preserves valid extracted values even when one field has a type mismatch.
    """
    warnings: List[Warning] = []
    normalized: Dict[str, Any] = {}

    for field_name, value in structured_fields.items():
        if field_name not in StructuredFields.model_fields:
            warnings.append(Warning(
                level="warning",
                message=f"Field '{field_name}' is not supported by StructuredFields and was ignored",
                field_name=field_name
            ))
            continue

        if value is None:
            continue

        if field_name in STRING_FIELDS:
            normalized_value, warning = _normalize_string_field(field_name, value)
        elif field_name == "allergies":
            normalized_value = _normalize_allergy_list(value)
            warning = None
        elif field_name in LIST_STRING_FIELDS:
            normalized_value, warning = _normalize_list_field(field_name, value)
        elif field_name in LIST_DICT_FIELDS:
            normalized_value, warning = _normalize_medication_field(field_name, value)
        elif field_name in DICT_FIELDS:
            normalized_value, warning = _normalize_dict_field(field_name, value)
        else:
            normalized_value, warning = value, None

        if warning is not None:
            warnings.append(warning)

        if normalized_value is not None:
            normalized[field_name] = normalized_value

    try:
        return StructuredFields(**normalized), warnings
    except Exception as exc:
        # This should be rare because we already coerced field-by-field, but keep a fallback.
        warnings.append(Warning(
            level="error",
            message=f"Structured field validation failed unexpectedly: {exc}",
            field_name=None
        ))
        return StructuredFields(), warnings


def validate_extracted_fields(
    structured_fields: Dict[str, Any],
    expected_fields: List[str]
) -> List[Warning]:
    """
    Validate extracted fields against expected fields.
    
    Returns:
        List of warnings for missing fields
    """
    warnings = []
    
    # Check for missing expected fields
    for field in expected_fields:
        if field not in structured_fields or structured_fields[field] is None:
            warnings.append(Warning(
                level="warning",
                message=f"Expected field '{field}' was not extracted or is null",
                field_name=field
            ))
    
    return warnings


def check_contradictions(
    structured_fields: Dict[str, Any],
    patient_data: Dict[str, Any]
) -> List[ContradictionFlag]:
    """
    Check for contradictions between extracted data and patient records.
    
    Returns:
        List of contradiction flags
    """
    contradictions = []
    
    # Check medications
    if "medications" in structured_fields and structured_fields["medications"]:
        patient_meds = patient_data.get("medications", [])
        if patient_meds:
            extracted_med_names = [
                med.get("name", "").lower() if isinstance(med, dict) else str(med).lower()
                for med in structured_fields["medications"]
            ]
            patient_med_names = [
                med.get("name", "").lower() if isinstance(med, dict) else str(med).lower()
                for med in patient_meds
            ]
            
            for extracted_med in structured_fields["medications"]:
                med_name = extracted_med.get("name", "") if isinstance(extracted_med, dict) else str(extracted_med)
                if med_name.lower() not in patient_med_names:
                    contradictions.append(ContradictionFlag(
                        field_name="medications",
                        user_text_value=extracted_med,
                        patient_record_value=patient_meds,
                        recommendation="Verify medication name and dosage against patient record",
                        severity="high"  # Medication mismatches are critical
                    ))
    
    # Check allergies
    if "allergies" in structured_fields and structured_fields["allergies"]:
        patient_allergies = patient_data.get("allergies", [])
        if patient_allergies:
            extracted_allergies_lower = [a.lower() for a in structured_fields["allergies"]]
            patient_allergies_lower = [a.lower() for a in patient_allergies]
            
            for allergy in structured_fields["allergies"]:
                if allergy.lower() not in patient_allergies_lower:
                    contradictions.append(ContradictionFlag(
                        field_name="allergies",
                        user_text_value=allergy,
                        patient_record_value=patient_allergies,
                        recommendation="Verify allergy against patient record",
                        severity="high"  # Allergy mismatches are critical
                    ))
    
    # Check vitals (if both exist, compare)
    if "vitals" in structured_fields and structured_fields["vitals"]:
        patient_vitals = patient_data.get("vitals", {})
        if patient_vitals:
            for vital_key, extracted_value in structured_fields["vitals"].items():
                if vital_key in patient_vitals and extracted_value is not None:
                    patient_value = patient_vitals[vital_key]
                    if str(extracted_value) != str(patient_value):
                        # Vitals mismatches are typically medium severity
                        # (can be upgraded to high for critical situations if needed)
                        # Critical vitals like BP, HR, O2 sat could be high, but defaulting to medium
                        # as vitals can vary and may not always indicate critical issues
                        contradictions.append(ContradictionFlag(
                            field_name=f"vitals.{vital_key}",
                            user_text_value=extracted_value,
                            patient_record_value=patient_value,
                            recommendation="Verify vital sign value against patient record",
                            severity="medium"
                        ))
    
    return contradictions


def deduplicate_contradictions(contradictions: List[ContradictionFlag]) -> List[ContradictionFlag]:
    """
    Deduplicate contradictions by creating a signature from field_name, user_text_value, and patient_record_value.
    Prefers specific field contradictions (e.g., vitals.bp) over general ones (e.g., vitals).
    Prefers contradictions with higher severity when duplicates exist.
    
    Args:
        contradictions: List of contradiction flags (may contain duplicates)
        
    Returns:
        Deduplicated list of contradictions, preferring specific over general
    """
    seen = {}
    deduplicated = []
    
    # First pass: collect all contradictions by signature
    for contradiction in contradictions:
        # Create signature: field_name + normalized values
        # Normalize values to strings for comparison
        user_val = str(contradiction.user_text_value) if contradiction.user_text_value is not None else "None"
        patient_val = str(contradiction.patient_record_value) if contradiction.patient_record_value is not None else "None"
        signature = f"{contradiction.field_name}|{user_val}|{patient_val}"
        
        # Normalize signature (lowercase, remove extra whitespace)
        signature = signature.lower().strip()
        
        # If we've seen this exact signature, prefer higher severity
        if signature in seen:
            existing = seen[signature]
            severity_order = {"high": 3, "medium": 2, "low": 1}
            
            if severity_order.get(contradiction.severity, 2) > severity_order.get(existing.severity, 2):
                # Replace with higher severity
                deduplicated.remove(existing)
                deduplicated.append(contradiction)
                seen[signature] = contradiction
        else:
            seen[signature] = contradiction
            deduplicated.append(contradiction)
    
    # Second pass: remove general contradictions if specific ones exist
    # e.g., if we have "vitals.bp" and "vitals.hr", remove "vitals" if it exists
    field_prefixes = {}  # Map base field to list of specific contradictions
    general_contradictions = []  # Contradictions without dots (general)
    
    for contradiction in deduplicated:
        if "." in contradiction.field_name:
            # Specific field (e.g., "vitals.bp")
            base_field = contradiction.field_name.split(".")[0]
            if base_field not in field_prefixes:
                field_prefixes[base_field] = []
            field_prefixes[base_field].append(contradiction)
        else:
            # General field (e.g., "vitals")
            general_contradictions.append(contradiction)
    
    # Remove general contradictions if we have specific ones for the same base field
    final_contradictions = []
    for contradiction in deduplicated:
        base_field = contradiction.field_name.split(".")[0] if "." in contradiction.field_name else contradiction.field_name
        
        # If this is a general contradiction and we have specific ones, skip it
        if "." not in contradiction.field_name and base_field in field_prefixes:
            # We have specific contradictions for this field, skip the general one
            continue
        
        final_contradictions.append(contradiction)
    
    return final_contradictions


def validate_json_structure(data: Dict[str, Any]) -> bool:
    """
    Validate that the AI response has the correct JSON structure.
    
    Returns:
        True if valid, raises ValueError if invalid
    """
    if not isinstance(data, dict):
        raise ValueError("Response must be a dictionary")
    
    if "structured_fields" not in data:
        raise ValueError("Response must contain 'structured_fields'")
    
    if not isinstance(data["structured_fields"], dict):
        raise ValueError("'structured_fields' must be a dictionary")
    
    return True

