"""Entity extraction service."""
import json
import re
import logging
from typing import Dict, Any, Optional, Any
from app.infrastructure.llm.llm_client import get_llm_client

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You are **MedAI Assistant**, an intelligent, professional hospital data assistant.
You help doctors, nurses, and administrators communicate naturally with hospital databases.
- Be polite, concise, and factual.
- Never invent data; only report what exists in the database.
- Always prefer patient_id when both name and ID are available.
- Understand pronouns like "he", "she", "their", or "this patient" using context.
- Add emojis to enhance the clarity of your output where appropriate. 🩺
"""


class EntityExtractionService:
    """Service for extracting entities from user messages."""
    
    def __init__(self, llm_client: Optional[Any] = None):
        self.llm_client = llm_client or get_llm_client()
        self._patient_id_re = re.compile(r"\bpatient\s*#?\s*(\d{1,10})\b", re.IGNORECASE)
    
    def extract_entities(self, text: str, session: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Extract entities (patient_name, patient_id, medicine, date).
        
        Args:
            text: User message
            session: Optional session context
            
        Returns:
            Dictionary with extracted entities
        """
        context_info = ""
        if session and (session.get("last_patient") or session.get("last_patient_id")):
            context_info = f"Context: last_patient={session.get('last_patient')}, last_patient_id={session.get('last_patient_id')}. "
        
        prompt = (
            f"{SYSTEM_PROMPT}\n{context_info}"
            "Extract entities as JSON: patient_name, patient_id, medicine, date.\n"
            "IMPORTANT: If a patient name is explicitly mentioned in the message, extract it as patient_name.\n"
            "Examples:\n"
            "- 'how old is furat?' → patient_name: 'furat'\n"
            "- 'is there a patient named John?' → patient_name: 'John'\n"
            "- 'what is mosa galib's age?' → patient_name: 'mosa galib'\n"
            "Do NOT use cached patient_id if a different name is mentioned in the query.\n"
            "Only use cached patient_id for pronouns like 'he', 'she', 'this patient' when no name is mentioned.\n"
            f"Message: {text}"
        )
        resp = self.llm_client.generate(prompt)
        try:
            return json.loads(resp) if resp.strip().startswith("{") else {}
        except Exception:
            return {}
    
    def extract_patient_id_simple(self, text: str) -> Optional[int]:
        """
        Heuristic extractor: 'patient 1003' -> 1003.
        
        Args:
            text: User message
            
        Returns:
            Patient ID or None
        """
        m = self._patient_id_re.search(text or "")
        if m:
            try:
                return int(m.group(1))
            except Exception:
                return None
        return None


# Global instance
_entity_service = EntityExtractionService()


def extract_entities_llama(text: str, session: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Legacy function for backward compatibility."""
    return _entity_service.extract_entities(text, session)


def extract_patient_id_simple(text: str) -> Optional[int]:
    """Legacy function for backward compatibility."""
    return _entity_service.extract_patient_id_simple(text)



