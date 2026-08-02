"""PHI detection and prevention."""

import re
from typing import Any, Dict, List


class AnonymizationChecker:
    """Checks for PHI in output."""

    PHI_PATTERNS = {
        "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
        "phone": r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
        "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        "mrn": r"\bMRN[:\s#-]*\d+\b",
        "address": r"\b\d+\s+[A-Za-z0-9\s]{2,40}\b(?:Street|St\.|Avenue|Ave\.|Road|Rd\.|Drive|Dr\.|Lane|Ln\.|Boulevard|Blvd\.|Court|Ct\.)\b",
        "provider_name": r"\b(?:Dr|Mr|Mrs|Ms)\.\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b",
    }

    REDACTIONS = {
        "ssn": "[REDACTED-SSN]",
        "phone": "[REDACTED-PHONE]",
        "email": "[REDACTED-EMAIL]",
        "mrn": "[REDACTED-MRN]",
        "address": "[REDACTED-ADDRESS]",
        "provider_name": "[REDACTED-NAME]",
    }

    def check_output(self, output: Dict[str, Any]) -> List[Dict[str, Any]]:
        issues = []
        for phi_type, pattern in self.PHI_PATTERNS.items():
            matches = self._find_matches(output, pattern)
            if matches:
                issues.append({"type": phi_type, "count": len(matches), "severity": "high"})
        return issues

    def sanitize_output(self, output: Dict[str, Any]) -> Dict[str, Any]:
        sanitized = self._sanitize_value(output)
        return sanitized if isinstance(sanitized, dict) else output

    def _find_matches(self, value: Any, pattern: str) -> List[str]:
        if isinstance(value, dict):
            matches: List[str] = []
            for key, item in value.items():
                if key in {"qa_method", "overall_score"}:
                    continue
                matches.extend(self._find_matches(item, pattern))
            return matches
        if isinstance(value, list):
            matches = []
            for item in value:
                matches.extend(self._find_matches(item, pattern))
            return matches
        if isinstance(value, str):
            return re.findall(pattern, value, re.IGNORECASE)
        return []

    def _sanitize_value(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {key: self._sanitize_value(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._sanitize_value(item) for item in value]
        if isinstance(value, str):
            sanitized = value
            for phi_type, pattern in self.PHI_PATTERNS.items():
                sanitized = re.sub(pattern, self.REDACTIONS[phi_type], sanitized, flags=re.IGNORECASE)
            return sanitized
        return value
