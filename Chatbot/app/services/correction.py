"""Spelling correction and query enhancement service."""
import logging
from typing import Tuple, Optional, Any
from difflib import SequenceMatcher
from app.infrastructure.llm.llm_client import get_llm_client

logger = logging.getLogger(__name__)


class SpellingCorrectionService:
    """Service for correcting spelling and enhancing queries."""
    
    def __init__(self, llm_client: Optional[Any] = None):
        self.llm_client = llm_client or get_llm_client()
    
    def correct_spelling_and_enhance_query(self, text: str) -> Tuple[str, bool]:
        """
        Spell correction with approval logic.
        
        Args:
            text: Input text to correct
            
        Returns:
            Tuple of (corrected_text, needs_approval)
        """
        try:
            prompt = f"""You are a spelling and grammar corrector. Correct the following text and return ONLY the corrected version. Do not add any labels, prefixes, or explanations.

Original text: {text}

Corrected text:"""
            raw_output = self.llm_client.generate(prompt).strip() or text
            
            # Clean up common LLM response patterns
            corrected = raw_output
            # Remove common prefixes (including "the corrected sentence:")
            import re
            # Remove patterns like "the corrected sentence:", "corrected sentence:", "here is the corrected:", etc.
            corrected = re.sub(r"^(the\s+)?(corrected\s+)?(sentence|text|answer|result)[:,\s]*", "", corrected, flags=re.IGNORECASE)
            corrected = re.sub(r"^(here\s+is|this\s+is|the\s+corrected|corrected|answer|result)[:,\s]*", "", corrected, flags=re.IGNORECASE)
            # Remove quotes if wrapped
            corrected = corrected.strip().strip('"').strip("'").strip()
            # Take first line if multiple lines
            corrected = corrected.split('\n')[0].strip()
            
            # If the cleaned output is empty or just contains the prompt text, use original
            if not corrected or corrected.lower() in ["the corrected sentence:", "corrected sentence:", "the corrected text:", "corrected text:"]:
                corrected = text
            
            ratio = SequenceMatcher(None, text.lower(), corrected.lower()).ratio()
            
            if corrected.lower().strip() == text.lower().strip():
                needs_approval = False
            elif ratio > 0.95:
                needs_approval = False
            else:
                needs_approval = True
            
            if corrected != text:
                logger.info(f"✏️  Corrected input: '{text}' → '{corrected}' (similarity={ratio:.2f})")
            
            return corrected or text, needs_approval
        except Exception as e:
            logger.warning(f"⚠️ Spell correction failed: {e}")
            return text, False


# Global instance
_correction_service = SpellingCorrectionService()


def correct_spelling_and_enhance_query(text: str) -> Tuple[str, bool]:
    """Legacy function for backward compatibility."""
    return _correction_service.correct_spelling_and_enhance_query(text)

