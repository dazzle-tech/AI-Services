"""Validator for QA response JSON."""

import json
from pathlib import Path
from typing import Dict, Any, Optional, Set, List
import jsonschema
from ..utils.json_utils import safe_json_loads

INVALID_TOP_LEVEL_KEYS: Set[str] = {
    "consistency",
    "safety",
    "completeness",
    "structure",
}

PARSED_REPORT_KEYS: Set[str] = {"format", "structure_used", "content", "unmapped_content"}
CONTENT_SECTIONS: Set[str] = {
    "patient_info",
    "encounter_summary",
    "diagnoses",
    "procedures_and_tests",
    "medications",
    "allergies",
    "vitals_and_key_results",
    "follow_up_and_instructions",
    "disposition",
    "providers_and_signoff",
}


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
            path = ".".join(str(part) for part in e.absolute_path) if e.absolute_path else "root"
            return False, f"Schema validation error at {path}: {e.message}"
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
        fixed = {
            key: value
            for key, value in response.copy().items()
            if key not in INVALID_TOP_LEVEL_KEYS
        }
        
        # Ensure all required keys exist
        if "qa_method" not in fixed:
            fixed["qa_method"] = "direct_qa"
        
        if "overall_score" not in fixed:
            fixed["overall_score"] = 0
        
        if "summary" not in fixed:
            fixed["summary"] = ""
        
        if "parsed_report" not in fixed:
            fixed["parsed_report"] = {}
        fixed["parsed_report"] = self._fix_parsed_report(fixed["parsed_report"])

        for key in ("errors", "missing_items", "inconsistencies", "recommended_corrections"):
            if key not in fixed:
                fixed[key] = []

        promoted_missing: List[Dict[str, Any]] = []
        schema_errors: List[Any] = []
        for error in fixed.get("errors", []):
            if isinstance(error, dict) and error.get("type") == "missing_item":
                promoted_missing.append(
                    {
                        "section": error.get("section", ""),
                        "field": error.get("field", ""),
                        "why_required": error.get("reason") or error.get("issue") or "",
                        "recommendation": error.get("recommendation", ""),
                    }
                )
            else:
                schema_errors.append(error)

        fixed["errors"] = self._fix_errors(schema_errors)
        merged_missing = self._merge_missing_items(
            list(fixed.get("missing_items", [])) + promoted_missing
        )
        fixed["missing_items"] = self._fix_missing_items(merged_missing)
        fixed["inconsistencies"] = self._fix_inconsistencies(fixed.get("inconsistencies", []))
        fixed["recommended_corrections"] = self._fix_corrections(fixed.get("recommended_corrections", []))

        # Ensure score is within bounds
        if isinstance(fixed.get("overall_score"), (int, float)):
            fixed["overall_score"] = max(0, min(100, fixed["overall_score"]))
        
        return fixed

    def _merge_missing_items(self, items: List[Any]) -> List[Dict[str, Any]]:
        merged: Dict[tuple[str, str], Dict[str, Any]] = {}
        for item in errors_or_items(items):
            if not isinstance(item, dict):
                continue
            key = (item.get("section", ""), item.get("field", ""))
            existing = merged.get(key)
            if existing is None:
                merged[key] = dict(item)
                continue
            for field in ("why_required", "recommendation", "required_by", "reason"):
                if not existing.get("why_required") and item.get(field):
                    if field == "reason":
                        existing["why_required"] = item[field]
                    elif field == "why_required":
                        existing["why_required"] = item[field]
                    else:
                        existing[field] = item[field]
        return list(merged.values())

    def _fix_parsed_report(self, parsed_report: Any) -> Dict[str, Any]:
        """Normalize parsed_report to the expected schema shape."""
        if not isinstance(parsed_report, dict):
            parsed_report = {}

        content = parsed_report.get("content") if isinstance(parsed_report.get("content"), dict) else {}

        for key, value in list(parsed_report.items()):
            if key in CONTENT_SECTIONS and value not in (None, {}, []):
                if key not in content or not content.get(key):
                    content[key] = value

        unmapped = parsed_report.get("unmapped_content")
        if not isinstance(unmapped, list):
            unmapped = []

        report_format = parsed_report.get("format", "text")
        if report_format not in ("json", "text"):
            report_format = "text"

        structure_used = parsed_report.get("structure_used", "standard")
        if structure_used not in ("template", "standard", "inferred"):
            structure_used = "standard"

        return {
            "format": report_format,
            "structure_used": structure_used,
            "content": content,
            "unmapped_content": unmapped,
        }

    def _fix_errors(self, errors: List[Any]) -> List[Dict[str, Any]]:
        fixed: List[Dict[str, Any]] = []
        valid_categories = {"completeness", "consistency", "safety", "structure"}
        valid_severities = {"low", "medium", "high", "critical"}

        for error in errors or []:
            if not isinstance(error, dict) or error.get("type") == "missing_item":
                continue
            location = error.get("location") if isinstance(error.get("location"), dict) else {}
            section = location.get("section") or error.get("section", "")
            field = location.get("field") or error.get("field", "")
            fixed.append(
                {
                    "id": error.get("id") or "",
                    "category": error.get("category") if error.get("category") in valid_categories else "completeness",
                    "severity": error.get("severity") if error.get("severity") in valid_severities else "low",
                    "location": {
                        "section": section,
                        "field": field,
                        "evidence_snippet": location.get("evidence_snippet", ""),
                    },
                    "issue": error.get("issue") or error.get("reason") or "",
                    "expected": error.get("expected", ""),
                    "observed": error.get("observed", ""),
                    "recommendation": error.get("recommendation", ""),
                    "references": error.get("references", []),
                }
            )
        return fixed

    def _fix_missing_items(self, items: List[Any]) -> List[Dict[str, Any]]:
        fixed: List[Dict[str, Any]] = []
        for item in errors_or_items(items):
            if not isinstance(item, dict):
                continue
            fixed.append(
                {
                    "id": item.get("id") or "",
                    "required_by": item.get("required_by")
                    if item.get("required_by") in {"template", "quality_rule"}
                    else "quality_rule",
                    "section": item.get("section", ""),
                    "field": item.get("field", ""),
                    "why_required": item.get("why_required") or item.get("reason") or "",
                    "recommendation": item.get("recommendation") or "",
                }
            )
        return fixed

    def _fix_inconsistencies(self, items: List[Any]) -> List[Dict[str, Any]]:
        fixed: List[Dict[str, Any]] = []
        valid_severities = {"low", "medium", "high", "critical"}
        valid_sources = {"patient_record", "onsite_doc"}

        for item in errors_or_items(items):
            if not isinstance(item, dict):
                continue
            fixed.append(
                {
                    "id": item.get("id") or "",
                    "severity": item.get("severity") if item.get("severity") in valid_severities else "medium",
                    "section": item.get("section", ""),
                    "field": item.get("field", ""),
                    "report_value": item.get("report_value", ""),
                    "source_value": item.get("source_value", ""),
                    "source": item.get("source") if item.get("source") in valid_sources else "patient_record",
                    "ref_id": item.get("ref_id", ""),
                    "recommendation": item.get("recommendation", ""),
                }
            )
        return fixed

    def _fix_corrections(self, items: List[Any]) -> List[Dict[str, Any]]:
        fixed: List[Dict[str, Any]] = []
        valid_actions = {"add", "remove", "replace", "rephrase"}

        for item in errors_or_items(items):
            if not isinstance(item, dict):
                continue
            if not item.get("section") or not item.get("field"):
                continue
            fixed.append(
                {
                    "id": item.get("id") or "",
                    "action": item.get("action") if item.get("action") in valid_actions else "add",
                    "section": item.get("section", ""),
                    "field": item.get("field", ""),
                    "suggested_text": item.get("suggested_text") or item.get("recommendation") or "",
                    "rationale": item.get("rationale") or item.get("why_required") or "",
                }
            )
        return fixed


def errors_or_items(items: Any) -> List[Any]:
    return items if isinstance(items, list) else []

