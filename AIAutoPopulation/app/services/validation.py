"""Validation and safety checks for extracted data."""
from typing import Dict, Any, List, Optional
from app.models.schemas import StructuredFields, UncertaintyFlag, ContradictionFlag, Warning
from app.core.constants import UserRole, ROLE_FIELD_RESTRICTIONS
from datetime import datetime


def validate_extracted_fields(
    structured_fields: Dict[str, Any],
    expected_fields: List[str],
    user_role: UserRole
) -> List[Warning]:
    """
    Validate extracted fields against expected fields and role restrictions.
    
    Returns:
        List of warnings for missing or restricted fields
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
    
    # Check role-based restrictions
    restricted_fields = ROLE_FIELD_RESTRICTIONS.get(user_role, [])
    for field in restricted_fields:
        if field in structured_fields and structured_fields[field] is not None:
            warnings.append(Warning(
                level="error",
                message=f"Field '{field}' is restricted for role '{user_role.value}' and should not be included",
                field_name=field
            ))
    
    return warnings


def apply_role_restrictions(
    structured_fields: Dict[str, Any],
    user_role: UserRole
) -> Dict[str, Any]:
    """
    Remove restricted fields based on user role.
    
    Returns:
        Filtered structured_fields dict
    """
    restricted_fields = ROLE_FIELD_RESTRICTIONS.get(user_role, [])
    filtered_fields = structured_fields.copy()
    
    for field in restricted_fields:
        if field in filtered_fields:
            del filtered_fields[field]
    
    return filtered_fields


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

