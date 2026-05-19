"""Intent detection service."""
import re
import logging
from typing import Dict, Any, Optional
from app.infrastructure.llm.llm_client import get_llm_client
from app.services.statistics.classifier import StatisticsIntentClassifier

logger = logging.getLogger(__name__)


class IntentDetectionService:
    """Service for detecting user intent (statistics, data, social, chat)."""
    
    def __init__(self, llm_client: Optional[Any] = None):
        self.llm_client = llm_client or get_llm_client()
    
    def detect_intent(self, text: str, session: Optional[Dict[str, Any]] = None) -> str:
        """
        Detect intent:
        - statistics: aggregate/non-patient analytics (counts, trends, top-N)
        - data: patient/clinical/database questions
        - chat: general conversation
        - social: greeting/thanks/farewell (merged)
        
        Args:
            text: User message
            session: Optional session context
            
        Returns:
            Intent string: "statistics", "data", "social", or "chat"
        """
        logger.info(f"🎯 Detecting intent for: {text}")
        
        tl = (text or "").strip().lower()
        
        # Fast deterministic SOCIAL guardrail
        social_patterns = [
            r"^(hi|hello|hey|good morning|good afternoon|good evening)\b",
            r"^(thanks|thank you|thx|ty)\b",
            r"^(bye|goodbye|see you|see ya|take care|farewell)\b",
        ]
        if any(re.search(p, tl) for p in social_patterns):
            return "social"
        
        if tl in {"morning", "evening", "hello!", "hi!", "hey!"}:
            return "social"

        # Deterministic STATISTICS guardrail (must run before DATA keyword checks).
        if StatisticsIntentClassifier.is_statistics_query(text):
            return "statistics"
        
        # Quick heuristic DATA guardrail
        data_keywords = [
            "who", "what", "when", "where", "how many", "how old", "how", "show", "get", "find", "list",
            "patient", "patients", "doctor", "nurse", "diagnosis", "disease",
            "admission", "admitted", "discharge", "dob", "date of birth",
            "result", "test", "treatment", "prescription", "medicine", "drug",
            "report", "record", "vitals", "temperature", "blood", "pressure",
            "heart rate", "pulse", "history", "condition", "status", "id",
            "ward", "room", "hospitalized", "injury", "lab", "x-ray", "scan", "allerg",
        ]
        pronouns = ["he", "she", "his", "her", "them", "this patient", "that patient"]
        
        # Check for age-related questions (e.g., "how old is X")
        age_patterns = [
            r"how old",
            r"what.*age",
            r"age.*\?",
        ]
        
        if any(k in tl for k in data_keywords) or any(p in tl for p in pronouns) or any(re.search(p, tl) for p in age_patterns):
            return "data"
        
        # LLM fallback (4-class). Deterministic rules above should cover statistics reliably.
        prompt = f"""
Classify this message strictly as ONE of:
- statistics: aggregate/non-patient analytics like top-N, distributions, trends, counts by, weekly/monthly totals.
- data: asking about patients, clinical records, admissions, diagnoses, tests, results, treatments.
- social: greeting, thanks, or farewell (hello/hi/thanks/bye).
- chat: everything else.

Return ONLY one word: statistics OR data OR social OR chat

Message: {text}
Answer:
"""
        result = (self.llm_client.generate(prompt) or "").lower().strip()
        
        # Normalize safely
        if "statistics" in result or "analytic" in result or "aggregate" in result:
            final = "statistics"
        elif "data" in result:
            final = "data"
        elif "social" in result or "greet" in result or "thank" in result or "farewell" in result or "bye" in result:
            final = "social"
        elif "chat" in result:
            final = "chat"
        else:
            final = "chat"
        
        logger.info(f"✅ Final Intent = {final}")
        return final


# Global instance
_intent_service = IntentDetectionService()


def detect_intent_llama(text: str, session: Optional[Dict[str, Any]] = None) -> str:
    """Legacy function for backward compatibility."""
    return _intent_service.detect_intent(text, session)


