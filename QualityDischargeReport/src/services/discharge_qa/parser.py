"""Parser for discharge reports."""

import logging
import re
from typing import Dict, Any, Optional, List, Tuple
from ...utils.json_utils import safe_json_loads

logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(levelname)s - %(name)s - %(message)s")
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
        "providers_and_signoff",
    ]

    SECTION_HEADER_RULES: List[Tuple[str, str]] = [
        ("patient_info", r"patient\s+information|demographics"),
        ("encounter_summary", r"chief\s+complaint"),
        ("encounter_summary", r"history\s+of\s+present\s+illness"),
        ("encounter_summary", r"hospital\s+course"),
        ("diagnoses", r"diagnos(?:is|es)"),
        ("procedures_and_tests", r"procedures?|tests?|imaging"),
        ("medications", r"medications?(?:\s+on\s+discharge)?|meds(?:\s+on\s+discharge)?|discharge\s+medications?"),
        ("allergies", r"allerg(?:y|ies)"),
        ("vitals_and_key_results", r"vitals?(?:\s+at\s+discharge)?|vital\s+signs"),
        ("follow_up_and_instructions", r"follow[- ]?up|return\s+precautions|discharge\s+instructions"),
        ("disposition", r"discharge\s+disposition|condition\s+on\s+discharge"),
        ("providers_and_signoff", r"service(?:\s+department)?|author|sign[- ]?off|provider"),
    ]

    def parse(self, content: Any, template: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if isinstance(content, str):
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

        normalized = self._normalize_structure(parsed, template)
        return {
            "format": format_type,
            "structure_used": structure_used,
            "content": normalized,
            "unmapped_content": [],
        }

    def _parse_text(self, text: str, template: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        sections = self._split_into_sections(text)
        result: Dict[str, Any] = {}

        for section_name, field_name, content in sections:
            if not content.strip():
                continue
            if field_name:
                section = result.setdefault(section_name, {})
                section[field_name] = content.strip()
                continue

            parsed = self._parse_section_content(section_name, content)
            if section_name in result and isinstance(result[section_name], dict) and isinstance(parsed, dict):
                result[section_name] = self._merge_section_dicts(result[section_name], parsed)
            else:
                result[section_name] = parsed

        return result

    def _split_into_sections(self, text: str) -> List[Tuple[str, Optional[str], str]]:
        inline_headers = re.finditer(
            r"(?im)^(service(?:\s+department)?|author|date)\s*:\s*(.+)$",
            text,
        )
        header_regex = re.compile(
            rf"(?im)^(?:{'|'.join(rule[1] for rule in self.SECTION_HEADER_RULES)})\s*:?\s*$"
        )
        boundaries = []

        for match in header_regex.finditer(text):
            boundaries.append((match.start(), match.end(), match.group(0).strip(), None))
        for match in inline_headers:
            header = match.group(1).strip()
            value = match.group(2).strip()
            boundaries.append((match.start(), match.end(), header, value))

        boundaries.sort(key=lambda item: item[0])
        sections: List[Tuple[str, Optional[str], str]] = []

        for index, (_, end, header_line, inline_value) in enumerate(boundaries):
            section_name, field_name = self._map_header_to_section(header_line)
            if inline_value is not None:
                sections.append((section_name, field_name, inline_value))
                continue
            start = end
            next_start = boundaries[index + 1][0] if index + 1 < len(boundaries) else len(text)
            chunk = text[start:next_start].strip()
            if chunk:
                sections.append((section_name, field_name, chunk))

        return sections

    def _map_header_to_section(self, header_line: str) -> Tuple[str, Optional[str]]:
        normalized = header_line.rstrip(":").strip()
        field_headers = {
            "chief_complaint": ("encounter_summary", "chief_complaint"),
            "history_of_present_illness": ("encounter_summary", "history_of_present_illness"),
            "hospital_course": ("encounter_summary", "hospital_course"),
            "return_precautions": ("follow_up_and_instructions", "return_precautions"),
            "discharge_disposition": ("disposition", "discharge_disposition"),
            "condition_on_discharge": ("disposition", "condition_on_discharge"),
        }
        for pattern, mapping in {
            r"chief\s+complaint": field_headers["chief_complaint"],
            r"history\s+of\s+present\s+illness": field_headers["history_of_present_illness"],
            r"hospital\s+course": field_headers["hospital_course"],
            r"return\s+precautions": field_headers["return_precautions"],
            r"discharge\s+disposition": field_headers["discharge_disposition"],
            r"condition\s+on\s+discharge": field_headers["condition_on_discharge"],
            r"service(?:\s+department)?": ("providers_and_signoff", "service_department"),
            r"author": ("providers_and_signoff", "author_role"),
            r"date": ("providers_and_signoff", "signoff_date"),
        }.items():
            if re.search(rf"(?i)^{pattern}$", normalized):
                return mapping

        for section_name, pattern in self.SECTION_HEADER_RULES:
            if re.search(rf"(?i)^{pattern}$", normalized):
                return section_name, None
        return normalized.replace(" ", "_"), None

    def _merge_section_dicts(self, left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(left)
        for key, value in right.items():
            if key not in merged or not merged[key]:
                merged[key] = value
            elif isinstance(merged[key], list) and isinstance(value, list):
                merged[key] = merged[key] + [item for item in value if item not in merged[key]]
        return merged

    def _parse_section_content(self, section_name: str, content: str) -> Dict[str, Any]:
        if section_name == "patient_info":
            return self._parse_patient_info(content)
        if section_name == "encounter_summary":
            return self._parse_encounter_summary(content)
        if section_name == "medications":
            return {"discharge_medications": self._extract_medications(content)}
        if section_name == "allergies":
            return {"allergies": self._extract_allergies(content)}
        if section_name == "diagnoses":
            return {
                "primary_diagnosis": self._extract_primary_diagnosis(content),
                "secondary_diagnoses": self._extract_secondary_diagnoses(content),
            }
        if section_name == "procedures_and_tests":
            return {"procedures": self._extract_list_items(content)}
        if section_name == "vitals_and_key_results":
            return {"vitals_last": self._extract_vitals(content), "key_results": []}
        if section_name == "follow_up_and_instructions":
            return self._parse_follow_up(content)
        if section_name == "disposition":
            return self._parse_disposition(content)
        if section_name == "providers_and_signoff":
            return self._parse_providers(content)
        return {"text": content.strip()} if content.strip() else {}

    def _parse_patient_info(self, content: str) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        age_match = re.search(r"age[:\s]+(\d+)", content, re.IGNORECASE)
        if age_match:
            result["age"] = int(age_match.group(1))
        sex_match = re.search(r"(?:sex|gender)[:\s]+([A-Za-z]+)", content, re.IGNORECASE)
        if sex_match:
            result["sex"] = sex_match.group(1)
        admission_match = re.search(r"admission\s+date[:\s]+([^\n]+)", content, re.IGNORECASE)
        if admission_match:
            result["admission_date"] = admission_match.group(1).strip()
        discharge_match = re.search(r"discharge\s+date[:\s]+([^\n]+)", content, re.IGNORECASE)
        if discharge_match:
            result["discharge_date"] = discharge_match.group(1).strip()
        return result

    def _parse_encounter_summary(self, content: str) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        if re.search(r"(?i)chief\s+complaint", content):
            result["chief_complaint"] = content.strip()
        elif re.search(r"(?i)history\s+of\s+present", content):
            result["history_of_present_illness"] = content.strip()
        elif re.search(r"(?i)hospital\s+course", content):
            result["hospital_course"] = content.strip()
        else:
            result["chief_complaint"] = content.strip()
        return result

    def _parse_follow_up(self, content: str) -> Dict[str, Any]:
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        appointments = []
        precautions = []
        for line in lines:
            if re.search(r"(?i)return|precaution|ed|emergency|warning", line):
                precautions.append(line)
            else:
                appointments.append(line)
        return {
            "follow_up_appointments": appointments,
            "return_precautions": precautions,
            "patient_instructions": content.strip(),
        }

    def _parse_disposition(self, content: str) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        if lines:
            result["discharge_disposition"] = lines[0]
        if len(lines) > 1:
            result["condition_on_discharge"] = lines[1]
        return result

    def _parse_providers(self, content: str) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        service_match = re.search(r"(?i)service(?:\s+department)?[:\s]+(.+)", content)
        if service_match:
            result["service_department"] = service_match.group(1).strip()
        author_match = re.search(r"(?i)author[:\s]+(.+)", content)
        if author_match:
            result["author_role"] = author_match.group(1).strip()
        date_match = re.search(r"(?i)date[:\s]+(.+)", content)
        if date_match:
            result["signoff_date"] = date_match.group(1).strip()
        return result

    def _extract_vitals(self, content: str) -> Dict[str, Any]:
        vitals: Dict[str, Any] = {}
        patterns = {
            "bp": r"bp[:\s]+([^\n,]+)",
            "hr": r"hr[:\s]+([^\n,]+)",
            "rr": r"rr[:\s]+([^\n,]+)",
            "temp": r"temp(?:erature)?[:\s]+([^\n,]+)",
            "o2_sat": r"(?:o2\s*sat|spo2)[:\s]+([^\n,]+)",
        }
        for key, pattern in patterns.items():
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                vitals[key] = match.group(1).strip()
        return vitals

    def _extract_list_items(self, content: str) -> List[str]:
        items = []
        for line in content.splitlines():
            line = line.strip().lstrip("-•").strip()
            if line and not line.endswith(":"):
                items.append(line)
        return items

    def _extract_medications(self, text: str) -> List[Dict[str, Any]]:
        meds = []
        for line in text.splitlines():
            line = line.strip()
            if not line or re.search(r"(?i)^(medications?|meds|on\s+discharge)[:\s]*$", line):
                continue
            if re.search(r"(?i)(on\s+discharge|discharge)[:\s]*$", line) and len(line) < 25:
                continue
            has_dose = re.search(
                r"(?i)(\d+\s*(?:mg|mcg|g|ml|units?|capsule|capsules|tablet|tablets|tabs?))",
                line,
            )
            if has_dose or line.startswith("-") or line.startswith("•"):
                meds.append({"name": line, "dose": None, "frequency": None, "route": None})
        return meds

    def _extract_allergies(self, text: str) -> List[str]:
        normalized = " ".join(text.split())
        if re.search(r"(?i)(nkda|no\s+known\s+(?:drug\s+)?allerg)", normalized):
            return ["No known drug allergies"]
        allergies = []
        for line in text.splitlines():
            line = line.strip().lstrip("-•").strip()
            if line and not re.search(r"(?i)^allerg", line):
                allergies.append(line)
        return allergies

    def _extract_primary_diagnosis(self, text: str) -> Optional[str]:
        match = re.search(r"(?i)primary[:\s]+(.+)", text)
        if match:
            return match.group(1).strip()
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return lines[0] if lines else None

    def _extract_secondary_diagnoses(self, text: str) -> List[str]:
        match = re.search(r"(?i)secondary[:\s]+(.+)", text)
        if match:
            return [part.strip() for part in re.split(r",|;", match.group(1)) if part.strip()]
        diagnoses = []
        for line in text.splitlines()[1:]:
            line = line.strip().lstrip("-•").strip()
            if line and not re.search(r"(?i)^primary", line):
                diagnoses.append(line)
        return diagnoses

    def _normalize_structure(self, parsed: Dict[str, Any], template: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        standard_structure = {section: {} for section in self.STANDARD_SECTIONS}
        for key, value in parsed.items():
            normalized_key = self._normalize_section_name(key)
            if normalized_key in standard_structure:
                standard_structure[normalized_key] = value
        return standard_structure

    def _normalize_section_name(self, name: str) -> str:
        name_lower = name.lower().replace(" ", "_").replace("-", "_")
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
            "discharge_disposition": "disposition",
            "procedures": "procedures_and_tests",
        }
        for key, value in mappings.items():
            if key in name_lower:
                return value
        return name_lower
