"""Parser for discharge reports."""

import logging
import json
import re
from typing import Dict, Any, Optional, List
from ...utils.json_utils import safe_json_loads, extract_json_from_text

logger = logging.getLogger(__name__)
# Ensure logger outputs to console
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(levelname)s - %(name)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)


class DischargeReportParser:
    """Parses discharge reports from text or JSON into structured format."""
    
    STANDARD_SECTIONS = [
        "patient_info",
        "encounter_summary",
        "diagnoses",
        "procedures_and_tests",
        "medications",
        "allergies",
        "vitals_and_key_results",
        "follow_up_and_instructions",
        "disposition",
        "providers_and_signoff"
    ]
    
    def parse(self, content: Any, template: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Parse discharge report content.
        
        Args:
            content: Text string or JSON object
            template: Optional template defining structure
            
        Returns:
            Parsed report structure
        """
        # Determine format
        if isinstance(content, str):
            # Try to parse as JSON first
            parsed = safe_json_loads(content)
            if isinstance(parsed, dict):
                format_type = "json"
                structure_used = "template" if template else "inferred"
            else:
                format_type = "text"
                structure_used = "template" if template else "standard"
                parsed = self._parse_text(content, template)
        else:
            format_type = "json"
            structure_used = "template" if template else "inferred"
            parsed = content if isinstance(content, dict) else {}
        
        # Normalize structure
        normalized = self._normalize_structure(parsed, template)
        
        return {
            "format": format_type,
            "structure_used": structure_used,
            "content": normalized,
            "unmapped_content": []
        }
    
    def _parse_text(self, text: str, template: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Parse text report into structured format."""
        result = {}
        
        if template:
            # Use template-defined sections
            sections = template.get("sections", [])
            for section in sections:
                section_name = section.get("name", "")
                result[section_name] = self._extract_section(text, section_name, section.get("patterns", []))
        else:
            # Use standard sections
            for section in self.STANDARD_SECTIONS:
                result[section] = self._extract_section(text, section)
        
        return result
    
    def _extract_section(self, text: str, section_name: str, patterns: Optional[List[str]] = None) -> Dict[str, Any]:
        """Extract section content from text."""
        # Common section header patterns
        section_patterns = {
            "patient_info": r"(?i)(patient\s+info|demographics|patient\s+demographics)",
            "encounter_summary": r"(?i)(encounter\s+summary|chief\s+complaint|history\s+of\s+present\s+illness|hospital\s+course)",
            "diagnoses": r"(?i)(diagnos(?:is|es)|final\s+diagnos(?:is|es))",
            "medications": r"(?i)(medication|medications|meds|discharge\s+medications)",
            "allergies": r"(?i)(allerg(?:y|ies)|allergic\s+reactions?)",
            "vitals": r"(?i)(vitals|vital\s+signs|vitals\s+and\s+key\s+results)",
            "follow_up": r"(?i)(follow\s+up|follow\s+up\s+instructions|discharge\s+instructions)",
            "disposition": r"(?i)(disposition|discharge\s+disposition)",
            "procedures": r"(?i)(procedures?|tests?|imaging)"
        }
        
        # Try to find section
        pattern = patterns[0] if patterns else section_patterns.get(section_name.lower().replace("_", " "), "")
        
        if pattern:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                # Extract content until next section or end
                start = match.end()
                # Find next section
                next_section_start = len(text)
                for other_pattern in section_patterns.values():
                    next_match = re.search(other_pattern, text[start:], re.IGNORECASE)
                    if next_match and next_match.start() < next_section_start:
                        next_section_start = next_match.start()
                
                content = text[start:start + next_section_start].strip()
                return self._parse_section_content(section_name, content)
        
        return {}
    
    def _parse_section_content(self, section_name: str, content: str) -> Dict[str, Any]:
        """Parse section content into structured fields."""
        result = {}
        
        # Basic field extraction based on section type
        if section_name == "patient_info":
            # Extract age, sex, dates
            age_match = re.search(r"age[:\s]+(\d+)", content, re.IGNORECASE)
            if age_match:
                result["age"] = int(age_match.group(1))
            
            sex_match = re.search(r"(?:sex|gender)[:\s]+([MFmf]|male|female)", content, re.IGNORECASE)
            if sex_match:
                result["sex"] = sex_match.group(1)
        
        elif section_name == "medications":
            # Extract medication list
            result["discharge_medications"] = self._extract_medications(content)
        
        elif section_name == "allergies":
            # Extract allergies
            result["allergies"] = self._extract_allergies(content)
        
        elif section_name == "diagnoses":
            # Extract diagnoses
            result["primary_diagnosis"] = self._extract_primary_diagnosis(content)
            result["secondary_diagnoses"] = self._extract_secondary_diagnoses(content)
        
        return result
    
    def _extract_medications(self, text: str) -> List[Dict[str, Any]]:
        """Extract medications from text."""
        logger.debug(f"_extract_medications called with text length: {len(text)}")
        meds = []
        # Simple line-by-line extraction
        lines = text.split('\n')
        logger.debug(f"Split into {len(lines)} lines")
        
        for i, line in enumerate(lines):
            original_line = line
            line = line.strip()
            
            # Skip empty lines, comments, and section headers
            if not line or line.startswith('#'):
                logger.debug(f"  Line {i+1}: Skipped (empty or comment)")
                continue
            
            # Skip section headers and labels
            if re.search(r"(?i)^(medications?|meds|discharge\s+medications?|home\s+medications?|on\s+discharge)[:\s]*$", line):
                logger.debug(f"  Line {i+1}: Skipped (section header): {line[:50]}")
                continue
            
            # Skip partial section headers (like "s on Discharge:" from "Medications on Discharge:")
            if re.search(r"(?i)(on\s+discharge|discharge)[:\s]*$", line) and len(line) < 25:
                logger.debug(f"  Line {i+1}: Skipped (partial section header): {line[:50]}")
                continue
            
            # Skip lines that are just colons or punctuation
            if re.match(r"^[:\-\s]+$", line):
                logger.debug(f"  Line {i+1}: Skipped (punctuation only): {line[:50]}")
                continue
            
            # Skip lines that look like headers (short, all caps, or ending with colon)
            if len(line) < 10 and (line.isupper() or line.endswith(':')):
                logger.debug(f"  Line {i+1}: Skipped (looks like header): {line[:50]}")
                continue
            
            # Skip lines that are just ":" or similar invalid patterns
            if re.match(r"^[:\s]+$", line) or line == ":":
                logger.debug(f"  Line {i+1}: Skipped (invalid pattern): {line[:50]}")
                continue
            
            # Only include lines that look like medication entries (contain dose or medication name)
            # Must have either: a dose pattern, or start with dash/bullet AND contain a medication-like word
            has_dose = re.search(r"(?i)(\d+\s*(?:mg|mcg|g|ml|units?)|[a-z]+\s+\d+)", line)
            has_med_name = re.search(r"(?i)\b(aspirin|metformin|lisinopril|atorvastatin|metoprolol|clopidogrel|warfarin|insulin|penicillin|amoxicillin|ibuprofen|acetaminophen|morphine|furosemide|omeprazole|levothyroxine|amlodipine|simvastatin|losartan|atenolol|propranolol|digoxin|prednisone|albuterol|sertraline|fluoxetine|gabapentin|tramadol|hydrochlorothiazide|carvedilol|spironolactone|folic|vitamin|calcium|iron|zinc|magnesium|potassium)\b", line)
            
            if has_dose or (line.startswith('-') or line.startswith('•')) and (has_dose or has_med_name):
                logger.debug(f"  Line {i+1}: Added as medication: {line[:50]}")
                meds.append({"name": line, "dose": None, "frequency": None, "route": None})
            else:
                logger.debug(f"  Line {i+1}: Skipped (doesn't look like medication): {line[:50]}")
        
        logger.debug(f"_extract_medications returning {len(meds)} medications")
        return meds
    
    def _extract_allergies(self, text: str) -> List[str]:
        """Extract allergies from text."""
        allergies = []
        # Look for "NKDA" or "No known allergies"
        if re.search(r"(?i)(nkda|no\s+known\s+allerg)", text):
            return []
        
        # Extract allergy items
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            if line:
                allergies.append(line)
        
        return allergies
    
    def _extract_primary_diagnosis(self, text: str) -> Optional[str]:
        """Extract primary diagnosis."""
        # Look for "Primary:" or first diagnosis
        match = re.search(r"(?i)primary[:\s]+(.+)", text)
        if match:
            return match.group(1).strip()
        
        # Take first line
        lines = text.split('\n')
        return lines[0].strip() if lines else None
    
    def _extract_secondary_diagnoses(self, text: str) -> List[str]:
        """Extract secondary diagnoses."""
        diagnoses = []
        lines = text.split('\n')
        for i, line in enumerate(lines):
            if i > 0:  # Skip first (primary)
                line = line.strip()
                if line:
                    diagnoses.append(line)
        return diagnoses
    
    def _normalize_structure(self, parsed: Dict[str, Any], template: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Normalize parsed structure to standard format."""
        normalized = {}
        
        # Standard structure
        standard_structure = {
            "patient_info": {},
            "encounter_summary": {},
            "diagnoses": {},
            "procedures_and_tests": {},
            "medications": {},
            "allergies": {},
            "vitals_and_key_results": {},
            "follow_up_and_instructions": {},
            "disposition": {},
            "providers_and_signoff": {}
        }
        
        # Map parsed content to standard structure
        for key, value in parsed.items():
            normalized_key = self._normalize_section_name(key)
            if normalized_key in standard_structure:
                normalized[normalized_key] = value
            else:
                # Store as unmapped
                pass
        
        # Fill in missing sections
        for section in standard_structure:
            if section not in normalized:
                normalized[section] = standard_structure[section]
        
        return normalized
    
    def _normalize_section_name(self, name: str) -> str:
        """Normalize section name to standard format."""
        name_lower = name.lower().replace(" ", "_").replace("-", "_")
        
        # Map common variations
        mappings = {
            "patient": "patient_info",
            "demographics": "patient_info",
            "encounter": "encounter_summary",
            "hpi": "encounter_summary",
            "diagnosis": "diagnoses",
            "medication": "medications",
            "meds": "medications",
            "allergy": "allergies",
            "vitals": "vitals_and_key_results",
            "followup": "follow_up_and_instructions",
            "instructions": "follow_up_and_instructions",
            "discharge_disposition": "disposition"
        }
        
        for key, value in mappings.items():
            if key in name_lower:
                return value
        
        return name_lower

