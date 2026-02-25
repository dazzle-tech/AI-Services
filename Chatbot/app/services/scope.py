"""Query scope detection service."""
import logging
from typing import Dict, Any, Optional, Any
from app.infrastructure.llm.llm_client import get_llm_client

logger = logging.getLogger(__name__)


class ScopeDetectionService:
    """Service for detecting query scope (specific vs general)."""
    
    def __init__(self, llm_client: Optional[Any] = None):
        self.llm_client = llm_client or get_llm_client()
    
    def decide_query_scope(self, message: str, session: Optional[Dict[str, Any]] = None) -> bool:
        """
        Decide whether the query refers to one specific patient (True)
        or all/multiple/general patients (False).
        
        Args:
            message: User message
            session: Optional session context
            
        Returns:
            True if specific patient, False if general
        """
        text_lower = (message or "").lower()
        
        # Heuristic: Check for GENERAL query patterns first (these override everything)
        import re
        general_patterns = [
            r"who\s+was\s+(discharged|admitted|released)",
            r"who\s+(was|were)\s+(discharged|admitted|released)",
            r"list\s+(of\s+)?(patients|discharges|admissions)",
            r"show\s+(me\s+)?(all|all\s+the)\s+patients",
            r"how\s+many\s+patients",
            r"which\s+patients",
            r"patients?\s+who\s+",
            r"all\s+patients",
        ]
        for pattern in general_patterns:
            if re.search(pattern, text_lower):
                logger.info(f"🧠 Heuristic: detected general query pattern '{pattern}' → GENERAL")
                return False
        
        # Heuristic: Check for specific patient patterns
        # Pattern: "patient 1003", "patient #1003", "patient ID 1003", etc.
        patient_id_pattern = re.compile(r"\bpatient\s*#?\s*(\d{1,10})\b", re.IGNORECASE)
        if patient_id_pattern.search(message):
            logger.info("🧠 Heuristic: detected specific patient ID in query → SPECIFIC")
            return True
        
        # Pattern: "how is patient X", "what is patient X", "show patient X"
        # Pronouns "he", "she", "this patient" indicate specific patient
        specific_patterns = [
            r"how\s+(is|are)\s+patient",
            r"what\s+(is|are)\s+patient",
            r"show\s+patient",
            r"patient\s+\d+",
            r"\b(this|that|the)\s+patient\b",
            r"\b(he|she|him|her)\s+(was|is|has|had)\b",  # "he was admitted", "she was discharged"
        ]
        for pattern in specific_patterns:
            if re.search(pattern, text_lower):
                logger.info(f"🧠 Heuristic: detected specific patient pattern '{pattern}' → SPECIFIC")
                return True
        
        if (
            ("list" in text_lower or "give me a list" in text_lower or "show me a list" in text_lower)
            and "patient" in text_lower
            and "their" in text_lower
            and "this patient" not in text_lower
            and "that patient" not in text_lower
        ):
            logger.info("🧠 Heuristic: treating 'list of patients ... with their ...' as GENERAL")
            return False
        
        prompt = f"""
You are MedAI Assistant, helping interpret medical data queries.

Decide whether the following hospital query refers to a specific patient or multiple/general patients.

Return only one word:
- "specific"
- "general"

Query: "{message}"
Answer:
"""
        result = self.llm_client.generate(prompt).strip().lower()
        return result.startswith("specific")
    
    def is_cohort_followup(self, text: str) -> bool:
        """
        Check if text refers to a cohort follow-up.
        
        Args:
            text: User message
            
        Returns:
            True if cohort follow-up
        """
        tl = (text or "").lower()
        phrases = [
            "these patients",
            "those patients",
            "the same patients",
            "the previous patients",
            "the above patients",
            "the listed patients",
            "these ones",
        ]
        return any(p in tl for p in phrases)


# Global instance
_scope_service = ScopeDetectionService()


def decide_query_scope_llama(message: str, session: Optional[Dict[str, Any]] = None) -> bool:
    """Legacy function for backward compatibility."""
    return _scope_service.decide_query_scope(message, session)


def is_cohort_followup(text: str) -> bool:
    """Legacy function for backward compatibility."""
    return _scope_service.is_cohort_followup(text)

