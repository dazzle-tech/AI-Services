"""Spelling correction and query enhancement service."""
import logging
import re
from typing import Tuple, Optional, Any
from difflib import SequenceMatcher
from app.infrastructure.llm.llm_client import get_llm_client
from app.services.mrn import extract_mrn

logger = logging.getLogger(__name__)


class SpellingCorrectionService:
    """Service for correcting spelling and enhancing queries."""

    PROTECTED_TERMS = {
        # Common hospital abbreviations/identifiers
        "mrn",
        "inpatient",
        "inpatients",
        "outpatient",
        "outpatients",
        "admission",
        "admissions",
        "discharge",
        "discharged",
        "diagnosis",
        "diagnoses",
        "allergy",
        "allergies",
        "icu",
        "ward",
        "er",
        "ed",
    }
    
    def __init__(self, llm_client: Optional[Any] = None):
        self.llm_client = llm_client or get_llm_client()

    def _extract_protected_terms(self, text: str) -> set[str]:
        text_lower = (text or "").lower()
        return {
            term
            for term in self.PROTECTED_TERMS
            if re.search(rf"\b{re.escape(term)}\b", text_lower)
        }

    def _extract_protected_identifiers(self, text: str) -> set[str]:
        """Preserve MRN-like alphanumeric identifiers such as P100."""
        return {
            match.group(0).lower()
            for match in re.finditer(r"\b[a-zA-Z]+[a-zA-Z0-9_-]*\d+[a-zA-Z0-9_-]*\b", text or "")
        }
    
    def correct_spelling_and_enhance_query(self, text: str) -> Tuple[str, bool]:
        """
        Spell correction with approval logic.
        
        Args:
            text: Input text to correct
            
        Returns:
            Tuple of (corrected_text, needs_approval)
        """
        try:
            prompt = f"""You are a spelling and grammar corrector for a hospital data assistant.
Correct only obvious spelling or grammar mistakes.
Preserve valid clinical and hospital terms exactly as written, including inpatient, inpatients, outpatient, ICU, diagnosis, allergies, ward, discharge, and admission.
Return ONLY the corrected version. Do not add any labels, prefixes, or explanations.

Original text: {text}

Corrected text:"""
            raw_output = self.llm_client.generate(prompt).strip() or text
            
            # Clean up common LLM response patterns
            corrected = raw_output
            # Remove common prefixes (including "the corrected sentence:")
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

            original_protected_terms = self._extract_protected_terms(text)
            corrected_protected_terms = self._extract_protected_terms(corrected)
            if not original_protected_terms.issubset(corrected_protected_terms):
                logger.info(
                    "🛡️ Preserving protected clinical terms. Original=%s Corrected=%s",
                    sorted(original_protected_terms),
                    sorted(corrected_protected_terms),
                )
                corrected = text
            
            original_identifiers = self._extract_protected_identifiers(text)
            corrected_identifiers = self._extract_protected_identifiers(corrected)
            if not original_identifiers.issubset(corrected_identifiers):
                logger.info(
                    "Preserving protected record identifiers. Original=%s Corrected=%s",
                    sorted(original_identifiers),
                    sorted(corrected_identifiers),
                )
                corrected = text

            # Hard safety: never allow correction to change MRN values.
            original_mrn = extract_mrn(text, allow_standalone=True)
            corrected_mrn = extract_mrn(corrected, allow_standalone=True)
            if original_mrn and corrected_mrn != original_mrn:
                logger.info(
                    "Preserving MRN identifier. Original=%s Corrected=%s",
                    original_mrn,
                    corrected_mrn,
                )
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
