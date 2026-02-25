"""Conflict resolver for document conflicts."""

from typing import List, Dict, Any, Optional
from ...domain.entities import OnsiteDoc
from ...utils.time_utils import compare_timestamps


class ConflictResolver:
    """Resolves conflicts between documents by preferring newer documents."""
    
    def resolve_conflicts(
        self,
        report_value: Any,
        source_values: List[Dict[str, Any]],
        source_docs: List[OnsiteDoc]
    ) -> Optional[Dict[str, Any]]:
        """Resolve conflicts by selecting the most recent source.
        
        Args:
            report_value: Value from discharge report
            source_values: List of {value, doc_id, timestamp} from sources
            source_docs: List of OnsiteDoc objects for reference
            
        Returns:
            Conflict info if conflict exists, None otherwise
        """
        if not source_values:
            return None
        
        # Sort by timestamp (newest first)
        sorted_sources = sorted(
            source_values,
            key=lambda x: x.get("timestamp", ""),
            reverse=True
        )
        
        most_recent = sorted_sources[0]
        most_recent_value = most_recent.get("value")
        
        # Check if report value conflicts with most recent source
        if self._values_differ(report_value, most_recent_value):
            return {
                "report_value": report_value,
                "source_value": most_recent_value,
                "source_doc_id": most_recent.get("doc_id"),
                "source_timestamp": most_recent.get("timestamp"),
                "severity": self._assess_conflict_severity(report_value, most_recent_value)
            }
        
        return None
    
    def _values_differ(self, val1: Any, val2: Any) -> bool:
        """Check if two values are meaningfully different."""
        if val1 is None and val2 is None:
            return False
        if val1 is None or val2 is None:
            return True
        
        # Normalize strings
        if isinstance(val1, str) and isinstance(val2, str):
            return val1.strip().lower() != val2.strip().lower()
        
        # Compare lists
        if isinstance(val1, list) and isinstance(val2, list):
            if len(val1) != len(val2):
                return True
            # Check if sets are different (order-independent)
            return set(str(v).lower() for v in val1) != set(str(v).lower() for v in val2)
        
        # Direct comparison
        return val1 != val2
    
    def _assess_conflict_severity(self, val1: Any, val2: Any) -> str:
        """Assess severity of conflict between values."""
        # Critical: medication conflicts, allergy conflicts
        if isinstance(val1, (str, list)) and isinstance(val2, (str, list)):
            val1_str = str(val1).lower()
            val2_str = str(val2).lower()
            
            # Medication-related conflicts
            if any(term in val1_str or term in val2_str for term in ["medication", "med", "drug", "dose"]):
                return "critical"
            
            # Allergy conflicts
            if any(term in val1_str or term in val2_str for term in ["allergy", "allergic"]):
                return "critical"
        
        # High: diagnosis conflicts
        if isinstance(val1, (str, list)) and isinstance(val2, (str, list)):
            val1_str = str(val1).lower()
            val2_str = str(val2).lower()
            if any(term in val1_str or term in val2_str for term in ["diagnosis", "diagnoses"]):
                return "high"
        
        # Medium: procedure conflicts
        if isinstance(val1, (str, list)) and isinstance(val2, (str, list)):
            val1_str = str(val1).lower()
            val2_str = str(val2).lower()
            if any(term in val1_str or term in val2_str for term in ["procedure", "test", "imaging"]):
                return "medium"
        
        # Low: other conflicts
        return "low"
    
    def get_most_recent_doc(self, docs: List[OnsiteDoc]) -> Optional[OnsiteDoc]:
        """Get the most recent document by timestamp."""
        if not docs:
            return None
        
        sorted_docs = sorted(
            docs,
            key=lambda d: d.timestamp,
            reverse=True
        )
        
        return sorted_docs[0]

