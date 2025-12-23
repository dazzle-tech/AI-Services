"""JSON utility functions."""

import json
from typing import Any, Dict


def safe_json_loads(text: str) -> Any:
    """Safely parse JSON string, return original if fails."""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return text


def extract_json_from_text(text: str) -> Any:
    """Try to extract JSON object from text that may contain markdown or extra text."""
    # Try to find JSON block
    start_idx = text.find('{')
    end_idx = text.rfind('}')
    
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        json_str = text[start_idx:end_idx + 1]
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass
    
    # Try parsing entire text
    return safe_json_loads(text)


def validate_json_structure(data: Dict[str, Any], required_keys: list) -> bool:
    """Check if dict has all required keys."""
    return all(key in data for key in required_keys)

