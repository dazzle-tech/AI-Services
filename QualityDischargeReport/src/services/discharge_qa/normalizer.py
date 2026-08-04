"""Normalizer for medications, vitals, and sections."""

import logging
import re
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)
# Ensure logger outputs to console
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(levelname)s - %(name)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)


_DOSE_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:mg|mcg|g|ml|units?|capsule|capsules|tablet|tablets|tabs?)\b",
    re.IGNORECASE,
)
_FREQ_PATTERNS: List[tuple[str, str]] = [
    ("three times daily", r"\bthree\s+times\s+daily\b"),
    ("twice daily", r"\btwice\s+daily\b"),
    ("once daily", r"\bonce\s+daily\b"),
    ("three times weekly", r"\bthree\s+times\s+(?:a\s+)?week(?:ly)?\b"),
    ("twice weekly", r"\btwice\s+(?:a\s+)?week(?:ly)?\b"),
    ("once weekly", r"\bonce\s+(?:a\s+)?week(?:ly)?\b"),
    ("weekly", r"\bweekly\b"),
    ("BID", r"\bBID\b"),
    ("TID", r"\bTID\b"),
    ("QID", r"\bQID\b"),
    ("daily", r"\bdaily\b"),
]
_EVERY_HOURS_PATTERN = re.compile(r"\bevery\s+\d+\s+hours?\b", re.IGNORECASE)
_MEDICATION_PREAMBLE = re.compile(
    r"(?i)^(?:the\s+)?patient\s+(?:is|was)\s+(?:prescribed|given|started\s+on|received)\s+"
)
_ON_ADMISSION_SUFFIX = re.compile(r"(?i)\s+on\s+admission\.?\s*$")
_ALLERGY_PREAMBLE = re.compile(r"(?i)^(?:the\s+)?patient\s+is\s+allergic\s+to\s+")


class DischargeReportNormalizer:
    """Normalizes discharge report content."""

    def normalize_medications(self, med_lines: List[Any]) -> List[Dict[str, Any]]:
        """Normalize medication entries.
        
        Expected format: {name, dose, frequency, route, duration, instructions}
        """
        logger.debug(f"normalize_medications called with {len(med_lines)} items")
        normalized = []
        
        for i, med in enumerate(med_lines):
            logger.debug(f"Processing medication {i+1}: {type(med)} - {str(med)[:50]}")
            
            if isinstance(med, str):
                logger.debug("  Type: string, parsing...")
                for segment in self._split_compound_medication_string(med):
                    parsed = self._parse_medication_string(segment)
                    logger.debug(
                        "  Parsed result: name=%s, dose=%s, route=%s, frequency=%s",
                        parsed.get("name"),
                        parsed.get("dose"),
                        parsed.get("route"),
                        parsed.get("frequency"),
                    )
                    normalized.append(parsed)
            elif isinstance(med, dict):
                logger.debug(f"  Type: dict, name={med.get('name')}, dose={med.get('dose')}, frequency={med.get('frequency')}")
                # If dict has name but other fields are None/missing, try parsing the name string
                if med.get("name") and (med.get("dose") is None and med.get("frequency") is None):
                    logger.debug(f"  Name has full string, parsing name: {med.get('name')[:50]}")
                    for segment in self._split_compound_medication_string(med.get("name", "")):
                        parsed = self._parse_medication_string(segment)
                        logger.debug(
                            "  Parsed from name: name=%s, dose=%s, route=%s, frequency=%s",
                            parsed.get("name"),
                            parsed.get("dose"),
                            parsed.get("route"),
                            parsed.get("frequency"),
                        )
                        parsed.update({k: v for k, v in med.items() if v is not None and k != "name"})
                        normalized.append(parsed)
                else:
                    logger.debug("  Using normalize_medication_dict")
                    normalized.append(self._normalize_medication_dict(med))
            else:
                logger.debug(f"  Type: other ({type(med)}), converting to string")
                normalized.append({"name": str(med), "dose": None, "frequency": None, "route": None})
        
        # Filter out invalid medications (those that couldn't be parsed and don't have valid names)
        filtered = []
        for med in normalized:
            name = med.get("name", "").strip()
            # Skip if name is empty, just punctuation, or looks like a header fragment
            if not name or re.match(r"^[:\-\s]+$", name) or name == ":":
                logger.debug(f"Filtering out invalid medication: {name[:50]}")
                continue
            # Skip if name looks like a section header fragment (e.g., "s on Discharge:", "on Discharge:")
            if re.search(r"(?i)^(on\s+discharge|discharge)[:\s]*$", name) and len(name) < 25:
                logger.debug(f"Filtering out header fragment: {name[:50]}")
                continue
            # Skip if name is too short and has no parsed fields (likely not a medication)
            if len(name) < 3 and not med.get("dose") and not med.get("frequency") and not med.get("route"):
                logger.debug(f"Filtering out too-short entry with no fields: {name[:50]}")
                continue
            # If it has dose, frequency, or route, it's probably valid - keep it
            # If it doesn't have those but the name looks reasonable (has letters and possibly numbers), keep it
            has_parsed_fields = med.get("dose") or med.get("frequency") or med.get("route")
            has_reasonable_name = len(name) >= 3 and re.search(r"[a-zA-Z]", name)
            if has_parsed_fields or has_reasonable_name:
                filtered.append(med)
            else:
                logger.debug(f"Filtering out entry with no parsed fields and unreasonable name: {name[:50]}")
        
        logger.debug(f"normalize_medications returning {len(filtered)} normalized medications (filtered {len(normalized) - len(filtered)} invalid)")
        return filtered

    def _split_compound_medication_string(self, med_str: str) -> List[str]:
        """Split narrative sentences that list multiple medications."""
        med_str = re.sub(r"^[-•*]\s*", "", med_str.strip())
        if not med_str or re.match(r"^[:\-\s]+$", med_str):
            return []

        cleaned = _MEDICATION_PREAMBLE.sub("", med_str).strip()
        cleaned = _ON_ADMISSION_SUFFIX.sub("", cleaned).strip()
        if not cleaned:
            return [med_str]

        parts = re.split(r"\s+and\s+", cleaned, flags=re.IGNORECASE)
        if len(parts) <= 1:
            return [cleaned]

        valid_parts = [part.strip() for part in parts if part.strip() and re.search(r"[a-zA-Z]", part)]
        if len(valid_parts) >= 2:
            return valid_parts
        return [cleaned]
    
    def _parse_medication_string(self, med_str: str) -> Dict[str, Any]:
        """Parse medication string into structured format."""
        logger.debug(f"_parse_medication_string called with: {med_str[:80]}")
        
        # Remove leading dashes, bullets, or whitespace
        original_str = med_str
        med_str = re.sub(r"^[-•*]\s*", "", med_str.strip())
        logger.debug(f"  After removing dashes: {med_str[:80]}")
        
        # Common patterns: "Medication 10mg PO BID" or "Medication, 10mg, PO, BID"
        result = {"name": med_str, "dose": None, "frequency": None, "route": None, "duration": None, "instructions": None}
        
        # Extract dose (e.g., "10mg", "500 mg", "3 Capsule")
        dose_match = _DOSE_PATTERN.search(med_str)
        if dose_match:
            result["dose"] = dose_match.group(0).strip()
            logger.debug(f"  Extracted dose: {result['dose']}")
            result["name"] = med_str.replace(dose_match.group(0), "").strip()
        else:
            logger.debug("  No dose found")
        
        # Extract route (PO, IV, IM, etc.) - check before removing from name
        route_patterns = ["PO", "IV", "IM", "SQ", "subcutaneous", "oral", "topical"]
        for route in route_patterns:
            route_match = re.search(rf"\b{route}\b", med_str, re.IGNORECASE)
            if route_match:
                result["route"] = route.upper() if len(route) <= 2 else route
                logger.debug(f"  Extracted route: {result['route']}")
                # Remove route from name
                result["name"] = result["name"].replace(route_match.group(0), "").strip()
                break
        
        # Extract frequency (BID, TID, daily, weekly, etc.)
        frequency, frequency_span = self._extract_frequency(med_str)
        if frequency:
            result["frequency"] = frequency
            logger.debug(f"  Extracted frequency: {result['frequency']}")
            if frequency_span:
                result["name"] = result["name"].replace(frequency_span, "").strip()
        
        # Clean up name - remove extra whitespace and common separators
        result["name"] = self._clean_medication_name(result["name"])
        
        logger.debug(f"  Final parsed result: name='{result['name']}', dose={result['dose']}, route={result['route']}, frequency={result['frequency']}")
        return result

    def _clean_medication_name(self, name: str) -> str:
        """Strip narrative preambles and trailing punctuation from medication names."""
        cleaned = _MEDICATION_PREAMBLE.sub("", name.strip()).strip()
        cleaned = cleaned.rstrip(".")
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        token_match = re.search(r"\b([A-Za-z][A-Za-z0-9_-]*)\s*\.?$", cleaned)
        if token_match and len(cleaned.split()) > 1:
            leading = cleaned[: token_match.start()].lower()
            if any(
                phrase in leading
                for phrase in ("patient", "prescribed", "given", "the ")
            ):
                return token_match.group(1)
        return cleaned

    def _extract_frequency(self, med_str: str) -> tuple[Optional[str], Optional[str]]:
        """Return normalized frequency label and matched source span."""
        every_hours_match = _EVERY_HOURS_PATTERN.search(med_str)
        if every_hours_match:
            return every_hours_match.group(0).strip(), every_hours_match.group(0)

        for freq, pattern in _FREQ_PATTERNS:
            freq_match = re.search(pattern, med_str, re.IGNORECASE)
            if freq_match:
                return freq, freq_match.group(0)
        return None, None

    def extract_frequency(self, med_str: str) -> Optional[str]:
        """Public helper for extracting a normalized frequency label."""
        frequency, _ = self._extract_frequency(med_str)
        return frequency

    def normalize_allergies(self, allergy_lines: List[Any]) -> List[str]:
        """Normalize allergy entries into comparable allergy terms."""
        normalized: List[str] = []
        for item in allergy_lines or []:
            if not item:
                continue
            text = str(item).strip()
            if re.search(r"(?i)(nkda|no\s+known\s+(?:drug\s+)?allerg)", text):
                normalized.append("No known drug allergies")
                continue
            text = re.sub(r"(?i)^allerg(?:y|ies)\s*:\s*", "", text).strip()
            text = _ALLERGY_PREAMBLE.sub("", text).strip().rstrip(".")
            for part in re.split(r"\s+and\s+|,", text, flags=re.IGNORECASE):
                part = part.strip()
                if part:
                    normalized.append(part)
        return normalized
    
    def _normalize_medication_dict(self, med: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize medication dictionary to standard format."""
        return {
            "name": med.get("name", ""),
            "dose": med.get("dose"),
            "frequency": med.get("frequency"),
            "route": med.get("route"),
            "duration": med.get("duration"),
            "instructions": med.get("instructions")
        }
    
    def normalize_vitals(self, vitals: Any) -> Dict[str, Optional[str]]:
        """Normalize vitals to standard format.
        
        Expected format: {bp, hr, rr, temp, o2_sat}
        """
        if isinstance(vitals, dict):
            return {
                "bp": str(vitals.get("bp", vitals.get("blood_pressure", ""))) if vitals.get("bp") or vitals.get("blood_pressure") else None,
                "hr": str(vitals.get("hr", vitals.get("heart_rate", ""))) if vitals.get("hr") or vitals.get("heart_rate") else None,
                "rr": str(vitals.get("rr", vitals.get("respiratory_rate", ""))) if vitals.get("rr") or vitals.get("respiratory_rate") else None,
                "temp": str(vitals.get("temp", vitals.get("temperature", ""))) if vitals.get("temp") or vitals.get("temperature") else None,
                "o2_sat": str(vitals.get("o2_sat", vitals.get("oxygen_saturation", ""))) if vitals.get("o2_sat") or vitals.get("oxygen_saturation") else None
            }
        elif isinstance(vitals, str):
            return self._parse_vitals_string(vitals)
        else:
            return {"bp": None, "hr": None, "rr": None, "temp": None, "o2_sat": None}
    
    def _parse_vitals_string(self, vitals_str: str) -> Dict[str, Optional[str]]:
        """Parse vitals string into structured format."""
        result = {"bp": None, "hr": None, "rr": None, "temp": None, "o2_sat": None}
        
        # Blood pressure: "120/80" or "BP: 120/80"
        bp_match = re.search(r"(?:BP|blood\s+pressure)[:\s]*(\d+/\d+)", vitals_str, re.IGNORECASE)
        if not bp_match:
            bp_match = re.search(r"(\d+/\d+)", vitals_str)
        if bp_match:
            result["bp"] = bp_match.group(1) if bp_match.lastindex else bp_match.group(0)
        
        # Heart rate: "HR: 72" or "72 bpm"
        hr_match = re.search(r"(?:HR|heart\s+rate)[:\s]*(\d+)", vitals_str, re.IGNORECASE)
        if not hr_match:
            hr_match = re.search(r"(\d+)\s*bpm", vitals_str, re.IGNORECASE)
        if hr_match:
            result["hr"] = hr_match.group(1) if hr_match.lastindex else hr_match.group(0)
        
        # Respiratory rate: "RR: 16" or "16/min"
        rr_match = re.search(r"(?:RR|respiratory\s+rate)[:\s]*(\d+)", vitals_str, re.IGNORECASE)
        if not rr_match:
            rr_match = re.search(r"(\d+)\s*/min", vitals_str, re.IGNORECASE)
        if rr_match:
            result["rr"] = rr_match.group(1) if rr_match.lastindex else rr_match.group(0)
        
        # Temperature: "Temp: 98.6" or "98.6 F"
        temp_match = re.search(r"(?:temp|temperature)[:\s]*(\d+(?:\.\d+)?)\s*[FC]?", vitals_str, re.IGNORECASE)
        if temp_match:
            result["temp"] = temp_match.group(1)
        
        # Oxygen saturation: "O2 Sat: 98%" or "SpO2: 98"
        o2_match = re.search(r"(?:O2\s+sat|SpO2|oxygen\s+saturation)[:\s]*(\d+)", vitals_str, re.IGNORECASE)
        if o2_match:
            result["o2_sat"] = o2_match.group(1)
        
        return result
    
    def normalize_section_names(self, content: Dict[str, Any], template: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Normalize section names to match template or standard format."""
        if template and "sections" in template:
            # Use template section names
            template_sections = {s.get("name", ""): s for s in template.get("sections", [])}
            normalized = {}
            
            for key, value in content.items():
                # Find matching template section
                matched = False
                for template_name, template_section in template_sections.items():
                    if key.lower() in template_name.lower() or template_name.lower() in key.lower():
                        normalized[template_name] = value
                        matched = True
                        break
                
                if not matched:
                    normalized[key] = value
            
            return normalized
        
        # Use standard section names
        return content

