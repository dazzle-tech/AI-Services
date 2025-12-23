"""Scoring logic for QA results."""

from typing import List, Dict, Any
from .types import Severity


class QAScorer:
    """Calculates overall quality score."""
    
    SCORE_PENALTIES = {
        Severity.CRITICAL: -25,
        Severity.HIGH: -15,
        Severity.MEDIUM: -7,
        Severity.LOW: -3
    }
    
    CRITICAL_SAFETY_CAP = 50
    
    def calculate_score(
        self,
        errors: List[Dict[str, Any]],
        missing_items: List[Dict[str, Any]],
        inconsistencies: List[Dict[str, Any]]
    ) -> int:
        """Calculate overall quality score.
        
        Args:
            errors: List of error objects
            missing_items: List of missing item objects
            inconsistencies: List of inconsistency objects
            
        Returns:
            Overall score (0-100)
        """
        score = 100
        
        # Apply penalties for errors
        for error in errors:
            severity = error.get("severity", "low")
            try:
                severity_enum = Severity(severity)
                score += self.SCORE_PENALTIES.get(severity_enum, 0)
            except ValueError:
                score += self.SCORE_PENALTIES[Severity.LOW]
        
        # Apply penalties for missing items (treat as medium severity)
        score += len(missing_items) * self.SCORE_PENALTIES[Severity.MEDIUM]
        
        # Apply penalties for inconsistencies
        for inconsistency in inconsistencies:
            severity = inconsistency.get("severity", "low")
            try:
                severity_enum = Severity(severity)
                score += self.SCORE_PENALTIES.get(severity_enum, 0)
            except ValueError:
                score += self.SCORE_PENALTIES[Severity.LOW]
        
        # Check for critical safety errors
        has_critical_safety = any(
            error.get("category") == "safety" and error.get("severity") == "critical"
            for error in errors
        )
        
        if has_critical_safety:
            score = min(score, self.CRITICAL_SAFETY_CAP)
        
        # Ensure score is between 0 and 100
        return max(0, min(100, score))
    
    def generate_summary(
        self,
        score: int,
        errors: List[Dict[str, Any]],
        missing_items: List[Dict[str, Any]],
        inconsistencies: List[Dict[str, Any]]
    ) -> str:
        """Generate summary text for QA results."""
        parts = []
        
        parts.append(f"Overall quality score: {score}/100.")
        
        error_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for error in errors:
            severity = error.get("severity", "low")
            if severity in error_counts:
                error_counts[severity] += 1
        
        if any(error_counts.values()):
            parts.append(f"Found {sum(error_counts.values())} errors: "
                        f"{error_counts['critical']} critical, {error_counts['high']} high, "
                        f"{error_counts['medium']} medium, {error_counts['low']} low.")
        
        if missing_items:
            parts.append(f"{len(missing_items)} required items are missing.")
        
        if inconsistencies:
            parts.append(f"{len(inconsistencies)} inconsistencies detected with source documents.")
        
        if score >= 90:
            parts.append("Report quality is excellent.")
        elif score >= 75:
            parts.append("Report quality is good with minor issues.")
        elif score >= 60:
            parts.append("Report quality is acceptable but requires improvements.")
        else:
            parts.append("Report quality is poor and requires significant corrections.")
        
        return " ".join(parts)

