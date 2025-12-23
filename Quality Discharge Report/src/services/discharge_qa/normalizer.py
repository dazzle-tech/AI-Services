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
                logger.debug(f"  Type: string, parsing...")
                parsed = self._parse_medication_string(med)
                logger.debug(f"  Parsed result: name={parsed.get('name')}, dose={parsed.get('dose')}, route={parsed.get('route')}, frequency={parsed.get('frequency')}")
                normalized.append(parsed)
            elif isinstance(med, dict):
                logger.debug(f"  Type: dict, name={med.get('name')}, dose={med.get('dose')}, frequency={med.get('frequency')}")
                # If dict has name but other fields are None/missing, try parsing the name string
                if med.get("name") and (med.get("dose") is None and med.get("frequency") is None):
                    logger.debug(f"  Name has full string, parsing name: {med.get('name')[:50]}")
                    # Name contains full medication string, parse it
                    parsed = self._parse_medication_string(med.get("name", ""))
                    logger.debug(f"  Parsed from name: name={parsed.get('name')}, dose={parsed.get('dose')}, route={parsed.get('route')}, frequency={parsed.get('frequency')}")
                    # Merge with any existing fields
                    parsed.update({k: v for k, v in med.items() if v is not None and k != "name"})
                    normalized.append(parsed)
                else:
                    logger.debug(f"  Using normalize_medication_dict")
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
    
    def _parse_medication_string(self, med_str: str) -> Dict[str, Any]:
        """Parse medication string into structured format."""
        logger.debug(f"_parse_medication_string called with: {med_str[:80]}")
        
        # Remove leading dashes, bullets, or whitespace
        original_str = med_str
        med_str = re.sub(r"^[-•*]\s*", "", med_str.strip())
        logger.debug(f"  After removing dashes: {med_str[:80]}")
        
        # Common patterns: "Medication 10mg PO BID" or "Medication, 10mg, PO, BID"
        result = {"name": med_str, "dose": None, "frequency": None, "route": None, "duration": None, "instructions": None}
        
        # Extract dose (e.g., "10mg", "500 mg", "10 mg")
        dose_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:mg|mcg|g|ml|units?)", med_str, re.IGNORECASE)
        if dose_match:
            result["dose"] = dose_match.group(0).strip()
            logger.debug(f"  Extracted dose: {result['dose']}")
            # Remove dose from name
            result["name"] = med_str.replace(dose_match.group(0), "").strip()
        else:
            logger.debug(f"  No dose found")
        
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
        
        # Extract frequency (BID, TID, QID, daily, etc.)
        freq_patterns = {
            "BID": r"\bBID\b",
            "TID": r"\bTID\b",
            "QID": r"\bQID\b",
            "daily": r"\bdaily\b",
            "once daily": r"\bonce\s+daily\b",
            "twice daily": r"\btwice\s+daily\b",
            "three times daily": r"\bthree\s+times\s+daily\b"
        }
        for freq, pattern in freq_patterns.items():
            freq_match = re.search(pattern, med_str, re.IGNORECASE)
            if freq_match:
                result["frequency"] = freq
                logger.debug(f"  Extracted frequency: {result['frequency']}")
                # Remove frequency from name
                result["name"] = result["name"].replace(freq_match.group(0), "").strip()
                break
        
        # Clean up name - remove extra whitespace and common separators
        result["name"] = re.sub(r"\s+", " ", result["name"]).strip()
        result["name"] = re.sub(r"^[,:\-]\s*", "", result["name"]).strip()
        
        logger.debug(f"  Final parsed result: name='{result['name']}', dose={result['dose']}, route={result['route']}, frequency={result['frequency']}")
        return result
    
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

