"""Validator for QA response JSON."""

import json
from pathlib import Path
from typing import Dict, Any, Optional
import jsonschema
from ..utils.json_utils import safe_json_loads


class ResponseValidator:
    """Validates JSON output against schema."""
    
    def __init__(self, schema_path: Optional[Path] = None):
        """Initialize validator.
        
        Args:
            schema_path: Path to JSON schema file (defaults to docs/schemas/discharge_qa.schema.json)
        """
        if schema_path is None:
            schema_path = Path(__file__).parent.parent.parent / "docs" / "schemas" / "discharge_qa.schema.json"
        
        self.schema_path = schema_path
        self.schema = self._load_schema()
    
    def _load_schema(self) -> Optional[Dict[str, Any]]:
        """Load JSON schema from file."""
        if self.schema_path and self.schema_path.exists():
            with open(self.schema_path, "r") as f:
                return json.load(f)
        return None
    
    def validate(self, response: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Validate response against schema.
        
        Args:
            response: Response dictionary to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if self.schema is None:
            # No schema, do basic validation
            return self._basic_validate(response)
        
        try:
            jsonschema.validate(instance=response, schema=self.schema)
            return True, None
        except jsonschema.ValidationError as e:
            return False, f"Schema validation error: {str(e)}"
        except Exception as e:
            return False, f"Validation error: {str(e)}"
    
    def _basic_validate(self, response: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Basic validation without schema."""
        required_keys = ["qa_method", "overall_score", "summary", "parsed_report", "errors", "missing_items", "inconsistencies", "recommended_corrections"]
        
        for key in required_keys:
            if key not in response:
                return False, f"Missing required key: {key}"
        
        # Validate score is number
        if not isinstance(response.get("overall_score"), (int, float)):
            return False, "overall_score must be a number"
        
        # Validate arrays
        for array_key in ["errors", "missing_items", "inconsistencies", "recommended_corrections"]:
            if not isinstance(response.get(array_key), list):
                return False, f"{array_key} must be an array"
        
        return True, None
    
    def fix_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Fix common issues in response."""
        fixed = response.copy()
        
        # Ensure all required keys exist
        if "qa_method" not in fixed:
            fixed["qa_method"] = "direct_qa"
        
        if "overall_score" not in fixed:
            fixed["overall_score"] = 0
        
        if "summary" not in fixed:
            fixed["summary"] = ""
        
        if "parsed_report" not in fixed:
            fixed["parsed_report"] = {
                "format": "unknown",
                "structure_used": "inferred",
                "content": {},
                "unmapped_content": []
            }
        
        for key in ["errors", "missing_items", "inconsistencies", "recommended_corrections"]:
            if key not in fixed:
                fixed[key] = []
        
        # Ensure score is within bounds
        if isinstance(fixed.get("overall_score"), (int, float)):
            fixed["overall_score"] = max(0, min(100, fixed["overall_score"]))
        
        return fixed

