"""PHI detection and prevention."""

import json
import re
from typing import List, Dict, Any


class AnonymizationChecker:
    """Checks for PHI in output."""
    
    # Common PHI patterns
    PHI_PATTERNS = {
        "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
        "phone": r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b",
        "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
        "mrn": r"\bMRN[:\s]*\d+\b",
        "address": r"\d+\s+[A-Za-z\s]+(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Lane|Ln|Boulevard|Blvd|Court|Ct)",
        "name": r"\b(?:Mr|Mrs|Ms|Dr)\.?\s+[A-Z][a-z]+\s+[A-Z][a-z]+\b"
    }
    
    def check_output(self, output: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Check output for PHI.
        
        Returns:
            List of PHI detection issues
        """
        issues = []
        output_str = str(output)
        
        for phi_type, pattern in self.PHI_PATTERNS.items():
            matches = re.findall(pattern, output_str, re.IGNORECASE)
            if matches:
                issues.append({
                    "type": phi_type,
                    "count": len(matches),
                    "severity": "high"
                })
        
        return issues
    
    def sanitize_output(self, output: Dict[str, Any]) -> Dict[str, Any]:
        """Remove PHI from output (basic implementation)."""
        output_str = json.dumps(output)
        
        # Replace SSNs
        output_str = re.sub(self.PHI_PATTERNS["ssn"], "[REDACTED-SSN]", output_str)
        
        # Replace phone numbers
        output_str = re.sub(self.PHI_PATTERNS["phone"], "[REDACTED-PHONE]", output_str)
        
        # Replace emails
        output_str = re.sub(self.PHI_PATTERNS["email"], "[REDACTED-EMAIL]", output_str)
        
        # Replace MRNs
        output_str = re.sub(self.PHI_PATTERNS["mrn"], "[REDACTED-MRN]", output_str)
        
        # Replace addresses
        output_str = re.sub(self.PHI_PATTERNS["address"], "[REDACTED-ADDRESS]", output_str)
        
        # Replace names (basic)
        output_str = re.sub(self.PHI_PATTERNS["name"], "[REDACTED-NAME]", output_str)
        
        try:
            return json.loads(output_str)
        except:
            return output

