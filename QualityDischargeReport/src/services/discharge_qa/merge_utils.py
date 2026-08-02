"""Helpers for merging QA findings."""

import re
from typing import Any, Dict, List


def _item_key(section: str, field: str) -> tuple[str, str]:
    return (section or "", field or "")


def _content_field_present(content: Dict[str, Any], section: str, field: str) -> bool:
    if not section:
        return False

    section_content = content.get(section)
    if section_content in (None, {}, []):
        return False

    if field in (None, "", section):
        if isinstance(section_content, dict):
            return len(section_content) > 0
        if isinstance(section_content, list):
            return len(section_content) > 0
        if isinstance(section_content, str):
            return bool(section_content.strip())
        return bool(section_content)

    if not isinstance(section_content, dict):
        return False

    value = section_content.get(field)
    if value is None:
        if section == "follow_up_and_instructions" and field == "return_precautions":
            instructions = section_content.get("patient_instructions", "")
            if isinstance(instructions, str) and re.search(
                r"(?i)(return to (?:the )?(?:ed|er|emergency)|return precautions|seek (?:immediate )?care)",
                instructions,
            ):
                return True
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return len(value) > 0
    return True


def filter_resolved_findings(qa_result: Dict[str, Any], content: Dict[str, Any]) -> Dict[str, Any]:
    """Remove findings for fields that are already present in merged report content."""
    filtered = dict(qa_result)

    filtered["missing_items"] = [
        item
        for item in filtered.get("missing_items", [])
        if isinstance(item, dict)
        and not _content_field_present(content, item.get("section", ""), item.get("field", ""))
    ]

    kept_errors = []
    for error in filtered.get("errors", []):
        if not isinstance(error, dict):
            continue
        if error.get("type") == "missing_item":
            continue
        location = error.get("location") or {}
        section = location.get("section") or error.get("section", "")
        field = location.get("field") or error.get("field", "")
        if _content_field_present(content, section, field):
            continue
        kept_errors.append(error)
    filtered["errors"] = kept_errors

    filtered["recommended_corrections"] = _ensure_corrections(
        [],
        filtered.get("missing_items", []),
        filtered.get("errors", []),
        filtered.get("inconsistencies", []),
    )

    return filtered


def normalize_content_sections(content: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize common AI/parser shape variations into standard section objects."""
    normalized = dict(content or {})

    procedures = normalized.get("procedures_and_tests")
    if isinstance(procedures, list):
        normalized["procedures_and_tests"] = {"procedures": [str(item) for item in procedures if item]}

    allergies = normalized.get("allergies")
    if isinstance(allergies, list):
        normalized["allergies"] = {"allergies": [str(item) for item in allergies if item]}

    vitals = normalized.get("vitals_and_key_results")
    if isinstance(vitals, dict):
        vitals_keys = {"bp", "hr", "rr", "temp", "o2_sat"}
        flat_vitals = {key: value for key, value in vitals.items() if key in vitals_keys and value}
        if flat_vitals:
            merged_vitals = dict(vitals)
            existing_last = merged_vitals.get("vitals_last") if isinstance(merged_vitals.get("vitals_last"), dict) else {}
            merged_last = dict(existing_last)
            for key, value in flat_vitals.items():
                merged_last.setdefault(key, value)
                merged_vitals.pop(key, None)
            merged_vitals["vitals_last"] = merged_last
            if "key_results" not in merged_vitals:
                merged_vitals["key_results"] = []
            normalized["vitals_and_key_results"] = merged_vitals

    return normalized


def deep_merge_content(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    """Merge overlay content into base, preserving non-empty values from either side."""
    merged = dict(base or {})
    for key, overlay_value in (overlay or {}).items():
        base_value = merged.get(key)
        if overlay_value in (None, {}, [], ""):
            continue
        if base_value in (None, {}, [], "") :
            merged[key] = overlay_value
        elif isinstance(base_value, dict) and isinstance(overlay_value, dict):
            if key == "medications":
                merged[key] = _merge_medications_section(base_value, overlay_value)
            else:
                merged[key] = deep_merge_content(base_value, overlay_value)
        elif isinstance(base_value, list) and isinstance(overlay_value, list):
            merged[key] = _merge_string_lists(base_value, overlay_value)
        else:
            merged[key] = base_value or overlay_value
    return merged


def _merge_medications_section(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    merged = deep_merge_content(base, overlay)
    if overlay.get("discharge_medications") and base.get("discharge_medications"):
        merged["discharge_medications"] = merge_medications(
            overlay.get("discharge_medications", []),
            base.get("discharge_medications", []),
        )
    return merged


def _merge_string_lists(base: List[Any], overlay: List[Any]) -> List[Any]:
    if not base:
        return overlay
    if not overlay:
        return base
    if all(isinstance(item, str) for item in base + overlay):
        base_text = " ".join(base).lower()
        overlay_text = " ".join(overlay).lower()
        if "no known" in overlay_text and "no known" in base_text and len(overlay_text) > len(base_text):
            return overlay
        if len(overlay) >= len(base) and len(overlay_text) >= len(base_text):
            return overlay
    return base if len(base) >= len(overlay) else overlay


def merge_findings(
    ai_result: Dict[str, Any],
    rule_findings: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Any]:
    merged = dict(ai_result)

    for key in ("errors", "missing_items", "inconsistencies", "recommended_corrections"):
        merged[key] = _merge_list(merged.get(key, []), rule_findings.get(key, []), key)

    merged["recommended_corrections"] = _ensure_corrections(
        merged.get("recommended_corrections", []),
        merged.get("missing_items", []),
        merged.get("errors", []),
        merged.get("inconsistencies", []),
    )
    return merged


def _merge_list(existing: List[Dict[str, Any]], incoming: List[Dict[str, Any]], kind: str) -> List[Dict[str, Any]]:
    merged = list(existing or [])
    seen = {_dedupe_key(item, kind) for item in merged}

    for item in incoming or []:
        key = _dedupe_key(item, kind)
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def _dedupe_key(item: Dict[str, Any], kind: str) -> tuple:
    if kind == "missing_items":
        return ("missing", item.get("section"), item.get("field"), item.get("required_by"))
    if kind == "inconsistencies":
        return ("inc", item.get("section"), item.get("field"), item.get("source"), str(item.get("source_value")))
    if kind == "errors":
        return ("err", item.get("category"), item.get("issue"))
    if kind == "recommended_corrections":
        return ("fix", item.get("section"), item.get("field"), item.get("action"))
    return ("other", str(item))


def _ensure_corrections(
    corrections: List[Dict[str, Any]],
    missing_items: List[Dict[str, Any]],
    errors: List[Dict[str, Any]],
    inconsistencies: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    result = list(corrections or [])
    seen = {_dedupe_key(item, "recommended_corrections") for item in result}

    for item in missing_items or []:
        correction = {
            "id": "",
            "action": "add",
            "section": item.get("section", ""),
            "field": item.get("field", ""),
            "suggested_text": item.get("recommendation", ""),
            "rationale": item.get("why_required", ""),
        }
        key = _dedupe_key(correction, "recommended_corrections")
        if key not in seen:
            seen.add(key)
            result.append(correction)

    for error in errors or []:
        location = error.get("location") or {}
        correction = {
            "id": "",
            "action": "replace" if error.get("observed") else "add",
            "section": location.get("section", ""),
            "field": location.get("field", ""),
            "suggested_text": error.get("recommendation", ""),
            "rationale": error.get("issue", ""),
        }
        key = _dedupe_key(correction, "recommended_corrections")
        if key not in seen:
            seen.add(key)
            result.append(correction)

    for item in inconsistencies or []:
        correction = {
            "id": "",
            "action": "add",
            "section": item.get("section", ""),
            "field": item.get("field", ""),
            "suggested_text": item.get("recommendation", ""),
            "rationale": f"Inconsistency with {item.get('source', 'source document')}",
        }
        key = _dedupe_key(correction, "recommended_corrections")
        if key not in seen:
            seen.add(key)
            result.append(correction)

    return result


def merge_medications(
    normalized_meds: List[Dict[str, Any]],
    ai_meds: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    ai_by_name = {
        str(med.get("name", "")).strip().lower(): med
        for med in ai_meds or []
        if isinstance(med, dict) and med.get("name")
    }
    merged: List[Dict[str, Any]] = []

    for med in normalized_meds or []:
        if not isinstance(med, dict):
            continue
        merged_med = dict(med)
        ai_med = ai_by_name.get(str(med.get("name", "")).strip().lower())
        if ai_med:
            for field in ("duration", "instructions", "status"):
                if not merged_med.get(field) and ai_med.get(field):
                    merged_med[field] = ai_med[field]
        merged.append(merged_med)

    return merged
