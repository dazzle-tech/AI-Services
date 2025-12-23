"""Spell correction utility for medical terms and vital signs."""
import re
from typing import Dict, List


class MedicalSpellCorrector:
    """Corrects common misspellings in medical text, especially vital signs."""
    
    def __init__(self):
        """Initialize with medical term corrections."""
        # Common misspellings for vital signs and medical terms
        self.corrections = {
            # Blood pressure variations
            r'\bblood\s+presure\b': 'blood pressure',
            r'\bblood\s+presure\b': 'blood pressure',
            r'\bbp\s+is\b': 'bp is',
            r'\bblood\s+pressure\s+is\b': 'blood pressure is',
            
            # Heart rate variations
            r'\bheart\s+reat\b': 'heart rate',
            r'\bheart\s+rae\b': 'heart rate',
            r'\bheart\s+rat\b': 'heart rate',
            r'\bhr\s+is\b': 'hr is',
            r'\bheart\s+rate\s+is\b': 'heart rate is',
            
            # Temperature variations
            r'\btemprature\b': 'temperature',
            r'\btemp\s+is\b': 'temp is',
            r'\btemperature\s+is\b': 'temperature is',
            r'\bfever\s+(\d+)': r'temperature \1',
            
            # Respiratory rate variations
            r'\brespiratory\s+reat\b': 'respiratory rate',
            r'\brespiratory\s+rae\b': 'respiratory rate',
            r'\brespiratory\s+rat\b': 'respiratory rate',
            r'\bresp\s+rate\b': 'respiratory rate',
            r'\brr\s+is\b': 'rr is',
            r'\brespiratory\s+rate\s+is\b': 'respiratory rate is',
            
            # Oxygen saturation variations
            r'\boxygen\s+saturation\b': 'oxygen saturation',
            r'\boxygen\s+sat\b': 'oxygen saturation',
            r'\bo2\s+sat\b': 'o2 sat',
            r'\bspo2\b': 'o2 sat',
            r'\boxygen\s+saturation\s+is\b': 'oxygen saturation is',
            
            # Common medical term misspellings
            r'\bmedication\b': 'medication',
            r'\bmedicaton\b': 'medication',
            r'\ballergy\b': 'allergy',
            r'\ballerg\b': 'allergy',
            r'\bdiagnosis\b': 'diagnosis',
            r'\bdiagnos\b': 'diagnosis',
            r'\bassessment\b': 'assessment',
            r'\bassessmnt\b': 'assessment',
            
            # Vital sign units and formats
            r'\b(\d+)\s*/\s*(\d+)\s*mm\s*hg\b': r'\1/\2',  # "150/90 mm hg" -> "150/90"
            r'\b(\d+)\s*/\s*(\d+)\s*mmhg\b': r'\1/\2',  # "150/90 mmhg" -> "150/90"
            r'\b(\d+)\s*b\s*p\s*m\b': r'\1 bpm',  # "95 b p m" -> "95 bpm"
            r'\b(\d+)\s*beats\s*per\s*minute\b': r'\1 bpm',  # "95 beats per minute" -> "95 bpm"
            r'\b(\d+)\s*degrees?\s*c\b': r'\1°C',  # "37 degrees c" -> "37°C"
            r'\b(\d+)\s*degrees?\s*f\b': r'\1°F',  # "98.6 degrees f" -> "98.6°F"
            r'\b(\d+)\s*percent\b': r'\1%',  # "98 percent" -> "98%"
            r'\b(\d+)\s*%\b': r'\1%',  # Ensure % is attached
        }
        
        # Common abbreviations that should be expanded for better extraction
        self.abbreviations = {
            r'\bbp\b(?!\s*is|\s*\d)': 'blood pressure',
            r'\bhr\b(?!\s*is|\s*\d)': 'heart rate',
            r'\btemp\b(?!\s*is|\s*\d)': 'temperature',
            r'\brr\b(?!\s*is|\s*\d)': 'respiratory rate',
            r'\bo2\s+sat\b': 'oxygen saturation',
        }
    
    def correct(self, text: str) -> str:
        """
        Correct misspellings in medical text.
        
        Args:
            text: Input text with potential misspellings
            
        Returns:
            Corrected text
        """
        corrected_text = text
        
        # Apply corrections (order matters - more specific first)
        for pattern, replacement in self.corrections.items():
            corrected_text = re.sub(pattern, replacement, corrected_text, flags=re.IGNORECASE)
        
        # Apply abbreviation expansions (optional - can be disabled if abbreviations are preferred)
        # Uncomment if you want to expand abbreviations
        # for pattern, replacement in self.abbreviations.items():
        #     corrected_text = re.sub(pattern, replacement, corrected_text, flags=re.IGNORECASE)
        
        return corrected_text
    
    def correct_vitals_section(self, text: str) -> str:
        """
        Specifically correct vital signs section of text.
        More aggressive correction for vital signs.
        
        Args:
            text: Input text
            
        Returns:
            Corrected text with vital signs normalized
        """
        corrected = self.correct(text)
        
        # Additional vital-specific corrections
        vital_corrections = {
            # Normalize blood pressure formats
            r'\b(\d{2,3})\s*over\s*(\d{2,3})\b': r'\1/\2',  # "150 over 90" -> "150/90"
            r'\b(\d{2,3})\s*slash\s*(\d{2,3})\b': r'\1/\2',  # "150 slash 90" -> "150/90"
            r'\b(\d{2,3})\s*-\s*(\d{2,3})\s*(?:mmhg|mm\s*hg)\b': r'\1/\2',  # "150-90 mmhg" -> "150/90"
            
            # Normalize heart rate formats
            r'\bheart\s+rate\s+of\s+(\d+)\b': r'heart rate \1 bpm',
            r'\bpulse\s+(\d+)\b': r'heart rate \1 bpm',
            r'\bhr\s+(\d+)\b': r'hr \1 bpm',
            
            # Normalize temperature formats
            r'\btemp\s+(\d+\.?\d*)\s*c\b': r'temp \1°C',
            r'\btemp\s+(\d+\.?\d*)\s*f\b': r'temp \1°F',
            r'\bfever\s+of\s+(\d+\.?\d*)\b': r'temp \1°F',
            
            # Normalize oxygen saturation
            r'\bo2\s+sat\s+(\d+)\s*%\b': r'o2 sat \1%',
            r'\bspo2\s+(\d+)\s*%\b': r'o2 sat \1%',
            r'\boxygen\s+(\d+)\s*%\b': r'oxygen saturation \1%',
            
            # Normalize respiratory rate
            r'\bresp\s+rate\s+(\d+)\b': r'respiratory rate \1 bpm',
            r'\brr\s+(\d+)\b': r'rr \1 bpm',
            r'\brespirations\s+(\d+)\b': r'respiratory rate \1 bpm',
        }
        
        for pattern, replacement in vital_corrections.items():
            corrected = re.sub(pattern, replacement, corrected, flags=re.IGNORECASE)
        
        return corrected


# Global instance
_spell_corrector = None


def get_spell_corrector() -> MedicalSpellCorrector:
    """Get or create the global spell corrector instance."""
    global _spell_corrector
    if _spell_corrector is None:
        _spell_corrector = MedicalSpellCorrector()
    return _spell_corrector


def correct_text(text: str, vitals_only: bool = False) -> str:
    """
    Convenience function to correct text.
    
    Args:
        text: Input text to correct
        vitals_only: If True, use more aggressive vital signs correction
        
    Returns:
        Corrected text
    """
    corrector = get_spell_corrector()
    if vitals_only:
        return corrector.correct_vitals_section(text)
    return corrector.correct(text)

