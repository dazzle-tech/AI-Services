"""Utilities for field path handling and validation."""
from typing import List, Set


def normalize_field_path(field_name: str) -> str:
    """
    Normalize field path to ensure consistent format.
    
    Examples:
        "vitals.temp" -> "vitals.temp"
        "medications[0].route" -> "medications[0].route"
        "temp" -> "temp" (if already top-level)
    """
    return field_name.strip()


def get_base_field(field_path: str) -> str:
    """
    Extract base field name from a path.
    
    Examples:
        "vitals.temp" -> "vitals"
        "medications[0].route" -> "medications"
        "chief_complaint" -> "chief_complaint"
    """
    if "." in field_path:
        return field_path.split(".")[0]
    if "[" in field_path:
        return field_path.split("[")[0]
    return field_path


def is_field_in_expected(field_path: str, expected_fields: List[str]) -> bool:
    """
    Check if a field path is related to an expected field.
    
    Args:
        field_path: Field path (e.g., "vitals.temp", "medications[0].route")
        expected_fields: List of expected top-level field names
        
    Returns:
        True if the field is related to an expected field
    """
    base_field = get_base_field(field_path)
    return base_field in expected_fields


def filter_uncertainty_flags_by_expected(
    uncertainty_flags: List,
    expected_fields: List[str],
    completeness_audit: bool = False
) -> List:
    """
    Filter uncertainty flags to only include those related to expected fields.
    
    Args:
        uncertainty_flags: List of uncertainty flag dicts or objects
        expected_fields: List of expected top-level field names
        completeness_audit: If True, include all flags; if False, only include expected ones
        
    Returns:
        Filtered list of uncertainty flags
    """
    if completeness_audit:
        return uncertainty_flags
    
    filtered = []
    for flag in uncertainty_flags:
        # Handle both dict and object types
        if isinstance(flag, dict):
            field_name = flag.get("field_name", "")
        else:
            field_name = getattr(flag, "field_name", "")
        
        if is_field_in_expected(field_name, expected_fields):
            filtered.append(flag)
    
    return filtered

