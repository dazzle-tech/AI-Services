"""Fill one EMR window's fields from transcribed speech (LLM or offline stub)."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from app.ai.client import AIClient
from app.ai.window_prompts import EXTRACTION_SYSTEM_PROMPT, build_extraction_prompt
from app.core.config import settings
from app.models.schemas import WindowExtractResponse
from app.models.window_schemas import (
    SITE_MARKING_STATUS_TO_MARKED,
    SIGN_OUT_CHECKLIST_TEMPLATE,
    TIME_OUT_CHECKLIST_TEMPLATE,
    VERIFICATION_CHECKLIST_TEMPLATE,
    WINDOW_SCHEMAS,
)

_ai_client: AIClient | None = None


def _get_ai_client() -> AIClient:
    global _ai_client
    if _ai_client is None:
        _ai_client = AIClient()
    return _ai_client


def extract_window_fields(
    window_id: str,
    text: str,
    existing_fields: dict | None,
    *,
    case_id: str,
    role: str,
) -> WindowExtractResponse:
    del role
    schema = WINDOW_SCHEMAS[window_id]
    prior = dict(existing_fields or {})

    if settings.use_llm_stub:
        raw_fields, low_confidence = _stub_extract(window_id, text, prior)
    else:
        prompt = build_extraction_prompt(window_id, schema, text, prior or None)
        raw = _get_ai_client().complete_json(
            model=settings.mapping_model,
            system_prompt=EXTRACTION_SYSTEM_PROMPT,
            user_prompt=prompt,
        )
        fields_payload = raw.get("fields", raw)
        low_confidence = list(raw.get("_low_confidence_fields") or [])
        raw_fields = fields_payload if isinstance(fields_payload, dict) else {}

    merged = _merge_fields(prior, raw_fields)
    if window_id == "nursing_intraoperative":
        merged = _normalize_intraoperative_fields(merged)

    dumped = schema.model_validate(merged).model_dump()
    if window_id == "nursing_verification_of_marking_site":
        dumped = _normalize_verification_fields(dumped)
    elif window_id == "nursing_time_out":
        dumped = _normalize_time_out_fields(dumped)
    elif window_id == "nursing_intraoperative":
        dumped = _normalize_intraoperative_fields(dumped)
    elif window_id == "nursing_sign_out":
        dumped = _normalize_sign_out_fields(dumped)
    elif window_id == "operative_note":
        dumped = _normalize_operative_note_fields(dumped)
    missing_fields = _missing_field_names(window_id, dumped)
    field_count = max(len(schema.model_fields), 1)
    needs_review = (len(missing_fields) > field_count / 2) or bool(low_confidence)
    if len(missing_fields) > field_count / 2:
        confidence = "low"
    elif low_confidence or missing_fields:
        confidence = "medium"
    else:
        confidence = "high"

    return WindowExtractResponse(
        case_id=case_id,
        window_id=window_id,
        fields=dumped,
        confidence=confidence,  # type: ignore[arg-type]
        needs_review=needs_review,
        missing_fields=missing_fields,
        raw_text=text,
    )


def _missing_field_names(window_id: str, dumped: Dict[str, Any]) -> List[str]:
    if window_id == "nursing_verification_of_marking_site":
        missing: List[str] = []
        for item in dumped.get("checklist") or []:
            if item.get("checked") is None:
                missing.append(item.get("key") or "checklist")
        marking = dumped.get("siteMarking") or {}
        if marking.get("status") in (None, "NOT_STATED"):
            missing.append("siteMarking")
        return missing
    if window_id == "nursing_time_out":
        missing = []
        for item in dumped.get("checklist") or []:
            if item.get("checked") is None:
                missing.append(item.get("key") or "checklist")
        staff = dumped.get("staff") or {}
        for role_key in ("surgeon", "nurse"):
            person = staff.get(role_key) or {}
            if not person.get("displayName") and not person.get("staffId"):
                missing.append(f"staff.{role_key}")
        return missing
    if window_id == "nursing_intraoperative":
        missing = []
        for name, value in dumped.items():
            if _intraoperative_section_empty(name, value):
                missing.append(name)
        return missing
    if window_id == "nursing_sign_out":
        missing = []
        for item in dumped.get("checklist") or []:
            if item.get("checked") is None:
                missing.append(item.get("key") or "checklist")
        return missing
    if window_id == "operative_note":
        missing = []
        for name, value in dumped.items():
            if _is_empty(value):
                missing.append(name)
            elif isinstance(value, dict) and all(_is_empty(v) for v in value.values()):
                missing.append(name)
        return missing
    return [name for name, value in dumped.items() if _is_empty(value)]


def _normalize_verification_fields(dumped: Dict[str, Any]) -> Dict[str, Any]:
    marking = dumped.get("siteMarking") or {}
    status = marking.get("status") or "NOT_STATED"
    if status not in SITE_MARKING_STATUS_TO_MARKED:
        status = "NOT_STATED"
    return {
        "checklist": _fill_checklist(VERIFICATION_CHECKLIST_TEMPLATE, dumped),
        "siteMarking": {
            "marked": SITE_MARKING_STATUS_TO_MARKED[status],
            "status": status,
            "note": marking.get("note") or "",
        },
    }


def _fill_checklist(template: list[dict], dumped: Dict[str, Any]) -> list[dict]:
    by_key = {}
    for item in dumped.get("checklist") or []:
        key = item.get("key")
        if key:
            by_key[key] = item
    filled = []
    for row in template:
        found = by_key.get(row["key"], {})
        filled.append(
            {
                "key": row["key"],
                "label": row["label"],
                "checked": found.get("checked"),
                "note": found.get("note") or "",
            }
        )
    return filled


def _fill_sign_out_checklist(template: list[dict], dumped: Dict[str, Any]) -> list[dict]:
    by_key = {}
    for item in dumped.get("checklist") or []:
        key = item.get("key")
        if key:
            by_key[key] = item
    filled = []
    for row in template:
        found = by_key.get(row["key"], {})
        filled.append(
            {
                "key": row["key"],
                "label": row["label"],
                "checked": found.get("checked"),
                "response": found.get("response"),
                "note": found.get("note") or "",
            }
        )
    return filled


def _normalize_sign_out_fields(dumped: Dict[str, Any]) -> Dict[str, Any]:
    return {"checklist": _fill_sign_out_checklist(SIGN_OUT_CHECKLIST_TEMPLATE, dumped)}


def _operative_note_empty() -> Dict[str, Any]:
    return {
        "operativeDetails": {"time": None, "typeOfAnesthesia": None},
        "operationStaff": {
            "mainSurgeon": None,
            "surgeonsAssistant": None,
            "surgicalStartTime": None,
            "surgicalEndTime": None,
        },
        "operationNote": None,
        "complication": None,
        "estimatedBloodLossMl": None,
    }


def _normalize_operative_note_fields(dumped: Dict[str, Any]) -> Dict[str, Any]:
    return _deep_merge(_operative_note_empty(), dumped or {})


def _normalize_time_out_fields(dumped: Dict[str, Any]) -> Dict[str, Any]:
    staff = dumped.get("staff") or {}
    surgeon = staff.get("surgeon") or {}
    nurse = staff.get("nurse") or {}
    return {
        "checklist": _fill_checklist(TIME_OUT_CHECKLIST_TEMPLATE, dumped),
        "staff": {
            "surgeon": {
                "staffId": surgeon.get("staffId"),
                "displayName": surgeon.get("displayName"),
            },
            "nurse": {
                "staffId": nurse.get("staffId"),
                "displayName": nurse.get("displayName"),
            },
        },
    }


def _intraoperative_empty() -> Dict[str, Any]:
    return {
        "operationStaff": {
            "date": None,
            "timeInToOperationRoom": None,
            "timeOutFromOperationRoom": None,
            "room": None,
            "scrubNurse1": None,
            "scrubNurse2": None,
            "circulateNurse1": None,
            "surgeon": None,
            "surgeonAssist1": None,
            "anesthesiologist": None,
        },
        "anesthesia": {"type": None},
        "position": {"position": None, "note": ""},
        "skinPreparationAndIncision": {"preparationSkinWith": None, "incisionSite": None},
        "foleyCatheter": {"na": None, "catheterSize": None, "urineOutputCc": None, "color": None},
        "tourniquet": {
            "na": None,
            "startTime": None,
            "endTime": None,
            "totalDurationMinutes": None,
            "pressureMmHg": None,
            "site": None,
        },
        "diathermiaAndLaser": {
            "na": None,
            "electroSurgicalUnit": None,
            "dispersiveElectrodeSite": None,
            "electroRangeCutting": None,
            "electroRangeCoagulation": None,
            "skinConditionBefore": None,
            "skinConditionAfter": None,
            "note": "",
        },
        "laser": {
            "na": None,
            "pulseEnergy": None,
            "frequency": None,
            "stoneEffect": None,
            "laserFiber": None,
            "note": "",
        },
        "drains": {"na": None, "entries": []},
        "specimens": {"na": None, "entries": []},
    }


def _deep_merge(base: Any, overlay: Any) -> Any:
    if overlay is None:
        return base
    if isinstance(base, dict) and isinstance(overlay, dict):
        merged = dict(base)
        for key, value in overlay.items():
            merged[key] = _deep_merge(base.get(key), value) if key in base else value
        return merged
    return overlay


def _normalize_intraoperative_fields(dumped: Dict[str, Any]) -> Dict[str, Any]:
    merged = _deep_merge(_intraoperative_empty(), dumped or {})
    for key in ("position", "diathermiaAndLaser", "laser"):
        block = merged.get(key) or {}
        if block.get("note") is None:
            block["note"] = ""
        merged[key] = block
    diathermia = merged.get("diathermiaAndLaser") or {}
    for key in ("electroRangeCutting", "electroRangeCoagulation"):
        value = diathermia.get(key)
        if value is not None and not isinstance(value, str):
            diathermia[key] = str(value)
    merged["diathermiaAndLaser"] = diathermia
    merged["drains"]["entries"] = merged["drains"].get("entries") or []
    merged["specimens"]["entries"] = merged["specimens"].get("entries") or []
    return merged


def _intraoperative_section_empty(name: str, value: Any) -> bool:
    if not isinstance(value, dict):
        return _is_empty(value)
    if name in ("drains", "specimens"):
        if value.get("na") is True:
            return False
        return not (value.get("na") is False and value.get("entries"))
    if name == "laser":
        if value.get("na") is True:
            return False
        return all(_is_empty(v) for k, v in value.items() if k != "note")
    if name in ("foleyCatheter", "tourniquet", "diathermiaAndLaser"):
        if value.get("na") is True:
            return False
        return all(_is_empty(v) for k, v in value.items() if k not in {"na", "note"})
    return all(_is_empty(v) for k, v in value.items() if k != "note")


def _is_empty(value: Any) -> bool:
    if value is None or value == "" or value == []:
        return True
    if isinstance(value, dict) and not any(not _is_empty(v) for v in value.values()):
        return True
    return False


def _merge_fields(existing: Dict[str, Any], extracted: Dict[str, Any]) -> Dict[str, Any]:
    if not existing:
        return extracted
    merged = dict(extracted)
    for key, prior in existing.items():
        if _is_empty(merged.get(key)) and not _is_empty(prior):
            merged[key] = prior
    return merged


def _flag(lower: str, *phrases: str) -> Optional[bool]:
    return True if any(p in lower for p in phrases) else None


def _after(text: str, pattern: str) -> Optional[str]:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1).strip(" .;,\n") or None


def _list_after(text: str, pattern: str) -> Optional[List[str]]:
    value = _after(text, pattern)
    if not value:
        return None
    parts = [p.strip() for p in re.split(r",| and ", value) if p.strip()]
    return parts or None


def _stub_extract(window_id: str, text: str, existing: Dict[str, Any]) -> tuple[Dict[str, Any], List[str]]:
    schema = WINDOW_SCHEMAS[window_id]
    fields: Dict[str, Any] = {name: None for name in schema.model_fields}
    lower = text.lower()
    extractor = _STUB_EXTRACTORS.get(window_id)
    if extractor:
        fields.update(extractor(text, lower))
    return _merge_fields(existing, fields), []


def _extract_verification(text: str, lower: str) -> Dict[str, Any]:
    def item(key: str, phrases: tuple[str, ...], note: str = "") -> dict:
        template = next(t for t in VERIFICATION_CHECKLIST_TEMPLATE if t["key"] == key)
        checked = True if any(p in lower for p in phrases) else None
        return {**template, "checked": checked, "note": note}

    consent_note = ""
    if "signed by patient" in lower:
        consent_note = "Signed by patient"
    elif "signed by" in lower:
        who = _after(text, r"signed by ([^.]+)") or ""
        consent_note = f"Signed by {who}" if who else ""

    if "patient refused" in lower or "refused marking" in lower:
        status = "NOT_MARKED_PATIENT_REFUSED"
        note = ""
    elif "single organ" in lower:
        status = "NOT_MARKED_SINGLE_ORGAN"
        note = ""
    elif "premature infant" in lower or ("teeth" in lower and "not mark" in lower):
        status = "NOT_MARKED_PREMATURE_INFANT_OR_TEETH"
        note = ""
    elif "site marked" in lower or "marked the site" in lower:
        status = "MARKED"
        raw_note = _after(text, r"site marked(?: on)?\s+([^.]+)") or _after(text, r"marked(?: on)?\s+([^.]+)") or ""
        note = re.sub(r"^(?:on\s+)?(?:the\s+)?", "", raw_note, flags=re.IGNORECASE).strip()
        if note:
            note = note[0].upper() + note[1:]
    else:
        status = "NOT_STATED"
        note = ""

    site_side_phrases = (
        "site / side / level",
        "site side level",
        "side / level",
        "level documented",
        "site and side",
        "laterality",
    )
    site_side_checked = True if any(p in lower for p in site_side_phrases) or (status == "MARKED" and note) else None

    checklist = [
        {**item("site_side_level_documented", ()), "checked": site_side_checked},
        item("pre_procedural_checklist_completed", ("pre-procedural check", "pre procedural check", "preprocedural check")),
        item(
            "procedure_surgical_consent_completed",
            ("procedure/surgical consent", "procedure surgical consent", "surgical consent", "procedure consent"),
            note=consent_note,
        ),
        item("anesthesia_consent_completed", ("anesthesia consent",)),
    ]

    return {
        "checklist": checklist,
        "siteMarking": {
            "status": status,
            "note": note,
            "marked": SITE_MARKING_STATUS_TO_MARKED[status],
        },
    }


def _extract_time_out(text: str, lower: str) -> Dict[str, Any]:
    def item(key: str, phrases: tuple[str, ...], note: str = "") -> dict:
        template = next(t for t in TIME_OUT_CHECKLIST_TEMPLATE if t["key"] == key)
        checked = True if any(p in lower for p in phrases) else None
        return {**template, "checked": checked, "note": note}

    patient_note = ""
    if "wristband" in lower:
        patient_note = "Confirmed by wristband"
    elif "confirmed by" in lower:
        patient_note = _after(text, r"confirmed by ([^.]+)") or ""
        if patient_note and not patient_note.lower().startswith("confirmed"):
            patient_note = f"Confirmed by {patient_note}"

    procedure_note = (
        _after(text, r"correct procedure[:\s]+([^.]+)")
        or _after(text, r"procedure[:\s]+((?:right|left)\s+[^.]+)")
        or ""
    )
    if procedure_note.lower().startswith("correct procedure"):
        procedure_note = procedure_note.split(" ", 2)[-1] if " " in procedure_note else procedure_note
    procedure_note = procedure_note.strip()
    if procedure_note:
        procedure_note = procedure_note[0].upper() + procedure_note[1:]

    position_note = _after(text, r"position[:\s]+([^.]+)") or ""
    if position_note.lower().startswith("correct"):
        position_note = re.sub(r"^correct\s+patient\s+position\s+", "", position_note, flags=re.IGNORECASE).strip()
    if position_note:
        position_note = position_note[0].upper() + position_note[1:]

    implant_note = (
        _after(text, r"(?:implants?|special equipment|tray)[:\s,]+([^.]+)")
        or _after(text, r"(size\s+\d+\s+tray[^.]+)")
        or ""
    )
    if implant_note.lower().startswith("size"):
        implant_note = implant_note[0].upper() + implant_note[1:]

    checklist = [
        item("correct_patient", ("correct patient", "patient confirmed"), note=patient_note),
        item("correct_procedure", ("correct procedure",), note=procedure_note),
        item("correct_site_and_side", ("correct site", "site and side")),
        item("correct_patient_position", ("correct patient position", "patient position"), note=position_note),
        item("verification_of_site_markings", ("verification of site marking", "site markings")),
        item(
            "availability_of_correct_implants_equipment",
            ("implants", "special equipment", "tray open", "correct implants"),
            note=implant_note,
        ),
    ]

    surgeon_name = _after(text, r"surgeon\s+(dr\.?\s+[A-Za-z][A-Za-z.'-]*(?:\s+[A-Za-z][A-Za-z.'-]*)*)")
    if surgeon_name:
        surgeon_name = re.split(r"\s+staff\s+id", surgeon_name, flags=re.IGNORECASE)[0].strip(" .,")
    nurse_name = _after(text, r"nurse\s+((?!staff)[A-Za-z][A-Za-z.'-]*(?:\s+[A-Za-z][A-Za-z.'-]*)*)")
    if nurse_name:
        nurse_name = re.split(r"\s+staff\s+id", nurse_name, flags=re.IGNORECASE)[0].strip(" .,")

    surgeon_id = _after(text, r"surgeon.*?staff id\s+(\S+)")
    nurse_id = _after(text, r"nurse.*?staff id\s+(\S+)")

    return {
        "checklist": checklist,
        "staff": {
            "surgeon": {"staffId": surgeon_id, "displayName": surgeon_name},
            "nurse": {"staffId": nurse_id, "displayName": nurse_name},
        },
    }


def _title_phrase(value: Optional[str]) -> Optional[str]:
    if not value:
        return value
    return value[0].upper() + value[1:]


def _extract_intraoperative(text: str, lower: str) -> Dict[str, Any]:
    def _int(pattern: str) -> Optional[int]:
        raw = _after(text, pattern)
        if not raw:
            return None
        digits = re.search(r"\d+", raw)
        return int(digits.group(0)) if digits else None

    def _map(value: Optional[str], table: Dict[str, str]) -> Optional[str]:
        if not value:
            return None
        key = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
        for needle, mapped in table.items():
            if needle in value.lower() or needle.replace("_", " ") in value.lower():
                return mapped
        return table.get(key) or value.upper().replace(" ", "_")

    def _name(pattern: str) -> Optional[str]:
        value = _after(text, pattern)
        if not value:
            return None
        value = value.strip(" .,")
        if value.lower().startswith("dr"):
            parts = value.split(".")
            if len(parts) >= 2:
                return ("Dr." + parts[1]).strip(" ,")
        return value.split(".")[0].strip(" ,")

    date = _after(text, r"(?:operation )?date\s+(\d{4}-\d{2}-\d{2})")
    time_in = _after(text, r"time in(?: to (?:the )?operation room)?\s+(\d{1,2}:\d{2})")
    time_out = _after(text, r"time out(?: from (?:the )?operation room)?\s+(\d{1,2}:\d{2})")
    room = _after(text, r"(?<!operation )room\s+(ROOM\s*\d+|[A-Za-z]*\d+)")
    if room:
        room = room.replace(" ", "").upper()

    anesthesia_raw = _after(text, r"anesthesia(?: type)?\s+([A-Za-z ]+)")
    position_raw = _after(text, r"position(?:ing)?\s+([A-Za-z]+)")
    prep_raw = _after(text, r"(?:prepared with|preparation skin with|skin prepared with)\s+([A-Za-z ]+)")

    foley_na = (
        True
        if re.search(r"foley.{0,40}(n/a|not used|not applicable)|(n/a|not used|not applicable).{0,20}foley", lower)
        else (False if "foley" in lower or re.search(r"catheter size", lower) else None)
    )
    tourniquet_na = (
        True
        if re.search(r"tourniquet.{0,40}(n/a|not used|not applicable)", lower)
        else (False if "tourniquet" in lower else None)
    )
    diathermia_mentioned = any(p in lower for p in ("diatherm", "electro surgical", "electrosurgical", "esu"))
    laser_na = True if "laser" in lower and any(p in lower for p in ("n/a", "not used", "not applicable", "no laser")) else (
        False if "laser" in lower and "not" not in lower else (True if "laser not" in lower else None)
    )
    if "laser not applicable" in lower or "no laser" in lower:
        laser_na = True

    start = _after(text, r"tourniquet start(?: time)?\s+(\d{1,2}:\d{2})") or _after(text, r"start(?: time)?\s+(\d{1,2}:\d{2})")
    end = _after(text, r"tourniquet end(?: time)?\s+(\d{1,2}:\d{2})") or _after(text, r"end(?: time)?\s+(\d{1,2}:\d{2})")
    duration = _int(r"(?:duration|total duration)\s+(\d+)")
    if duration is None and start and end:
        sh, sm = [int(x) for x in start.split(":")]
        eh, em = [int(x) for x in end.split(":")]
        duration = (eh * 60 + em) - (sh * 60 + sm)

    drains: list[dict] = []
    if "hemovac" in lower:
        drains.append(
            {
                "type": "HEMOVAC",
                "numberOfDrains": _int(r"hemovac(?: drain)?s?\s+(\d+)") or _int(r"(\d+)\s+hemovac"),
                "location": _title_phrase(_after(text, r"hemovac[^.]*?(?:at|location)\s+([^.]+)")),
                "size": None,
                "otherLabel": None,
            }
        )
    if "chest tube" in lower:
        chest_size = _int(r"chest tube(?: size)?\s+(\d+)")
        chest_location = _after(text, r"chest tube(?: size \d+)?\s+([A-Za-z][^.]*)")
        if chest_location and chest_size is not None:
            chest_location = re.sub(rf"^size\s+{chest_size}\s+", "", chest_location, flags=re.IGNORECASE).strip()
        drains.append(
            {
                "type": "CHEST_TUBE",
                "numberOfDrains": _int(r"chest tubes?\s+(\d+)"),
                "location": _title_phrase(chest_location),
                "size": chest_size,
                "otherLabel": None,
            }
        )
    if "blake" in lower or "other drain" in lower:
        blake_location = _after(text, r"(?:blake drain|other drain)[^.]*?(?:subcutaneous,\s*)?([^.]+)")
        if blake_location:
            blake_location = re.sub(r"^blake drain\s+\d+\s+", "", blake_location, flags=re.IGNORECASE).strip(" ,")
            if not blake_location.lower().startswith("subcutaneous"):
                blake_location = f"Subcutaneous, {blake_location}"
        drains.append(
            {
                "type": "OTHERS",
                "numberOfDrains": _int(r"(?:blake|other drain)[^\d]*(\d+)") or 1,
                "location": _title_phrase(blake_location),
                "size": None,
                "otherLabel": "Blake drain" if "blake" in lower else _after(text, r"other drain\s+([^.]+)"),
            }
        )

    specimens: list[dict] = []
    if "pathology" in lower:
        specimens.append(
            {
                "type": "PATHOLOGY",
                "numberOfSamples": _int(r"pathology(?: specimens?)?\s+(\d+)") or _int(r"(\d+)\s+pathology"),
                "location": _title_phrase(_after(text, r"pathology[^.]*?(?:at|,)\s+([^.]+)")),
                "otherLabel": None,
                "description": None,
            }
        )
    if "frozen section" in lower:
        specimens.append(
            {
                "type": "FROZEN_SECTION",
                "numberOfSamples": _int(r"frozen section\s+(\d+)") or 1,
                "location": _title_phrase(_after(text, r"frozen section[^.]*?(?:at|,)\s+([^.]+)")),
                "otherLabel": None,
                "description": None,
            }
        )
    if "removed organ" in lower or "meniscal" in lower or "excised" in lower:
        specimens.append(
            {
                "type": "REMOVED_ORGAN_DESCRIPTION",
                "numberOfSamples": 1,
                "location": None,
                "otherLabel": None,
                "description": _title_phrase(
                    _after(text, r"(?:removed organ description|excised)\s+([^.]+)")
                ),
            }
        )

    position_note = ""
    if "tucked" in lower or "padding" in lower or "heels" in lower:
        position_note = _after(text, r"(left arm tucked[^.]+|padding[^.]+)") or ""
        extra = []
        if "left arm tucked" in lower:
            extra.append("Left arm tucked")
        if "padding" in lower:
            extra.append(_after(text, r"(padding at [^.]+)") or "padding at both heels")
        position_note = ", ".join(dict.fromkeys(extra)) if extra else position_note

    return {
        "operationStaff": {
            "date": date,
            "timeInToOperationRoom": time_in,
            "timeOutFromOperationRoom": time_out,
            "room": room,
            "scrubNurse1": _name(r"scrub nurse 1\s+([A-Za-z][A-Za-z.'-]*(?:\s+[A-Za-z][A-Za-z.'-]*)*)"),
            "scrubNurse2": _name(r"scrub nurse 2\s+([A-Za-z][A-Za-z.'-]*(?:\s+[A-Za-z][A-Za-z.'-]*)*)"),
            "circulateNurse1": _name(r"circulate(?: circulating)? nurse 1\s+([A-Za-z][A-Za-z.'-]*(?:\s+[A-Za-z][A-Za-z.'-]*)*)"),
            "surgeon": _name(r"(?<!assist 1 )surgeon\s+(dr\.?\s+[A-Za-z][A-Za-z.'-]*(?:\s+[A-Za-z][A-Za-z.'-]*)*)"),
            "surgeonAssist1": _name(r"surgeon assist(?:ant)? 1\s+(dr\.?\s+[A-Za-z][A-Za-z.'-]*(?:\s+[A-Za-z][A-Za-z.'-]*)*)"),
            "anesthesiologist": _name(r"anesthesiologist\s+(dr\.?\s+[A-Za-z][A-Za-z.'-]*(?:\s+[A-Za-z][A-Za-z.'-]*)*)"),
        },
        "anesthesia": {
            "type": _map(anesthesia_raw, {"general": "GENERAL", "spinal": "SPINAL", "epidural": "EPIDURAL", "regional": "REGIONAL", "local": "LOCAL", "mac": "MAC"}),
        },
        "position": {
            "position": _map(position_raw, {"supine": "SUPINE", "prone": "PRONE", "lateral": "LATERAL", "lithotomy": "LITHOTOMY", "beach": "BEACH_CHAIR", "sitting": "SITTING"}),
            "note": position_note,
        },
        "skinPreparationAndIncision": {
            "preparationSkinWith": _map(prep_raw, {"povidone": "POVIDONE_IODINE", "betadine": "POVIDONE_IODINE", "chlorhexidine": "CHLORHEXIDINE", "alcohol": "ALCOHOL"}),
            "incisionSite": _title_phrase(_after(text, r"incision site\s+([^.]+)")),
        },
        "foleyCatheter": {
            "na": foley_na,
            "catheterSize": _int(r"(?:foley )?(?:catheter )?size\s+(\d+)"),
            "urineOutputCc": _int(r"urine output\s+(\d+)"),
            "color": _title_phrase(_after(text, r"(?:urine )?(?:color|colour)\s+([^.]+)")),
        },
        "tourniquet": {
            "na": tourniquet_na,
            "startTime": start if "tourniquet" in lower else None,
            "endTime": end if "tourniquet" in lower else None,
            "totalDurationMinutes": duration if "tourniquet" in lower else None,
            "pressureMmHg": _int(r"pressure\s+(\d+)"),
            "site": _title_phrase(
                _after(text, r"tourniquet[^.]*site\s+([^.]+)") or _after(text, r"pressure[^.]*site\s+([^.]+)")
            ),
        },
        "diathermiaAndLaser": {
            "na": False if diathermia_mentioned else None,
            "electroSurgicalUnit": _after(text, r"(?:electro surgical unit|electrosurgical unit|esu)\s+(\S+)"),
            "dispersiveElectrodeSite": _title_phrase(
                _after(text, r"dispersive electrode(?: site)?\s+([^.]+?)(?:,\s*cutting|$)")
            ),
            "electroRangeCutting": _after(text, r"cutting\s+(\d+)"),
            "electroRangeCoagulation": _after(text, r"coagulation\s+(\d+)"),
            "skinConditionBefore": (
                "Intact, no " + skin_before[9:].lstrip()
                if (skin_before := _after(text, r"skin (?:condition )?before\s+([^.]+?)(?:,\s*skin after|$)"))
                and skin_before.lower().startswith("intact no")
                else _title_phrase(
                    _after(text, r"skin (?:condition )?before\s+([^.]+?)(?:,\s*skin after|$)")
                )
            ),
            "skinConditionAfter": _title_phrase(_after(text, r"skin (?:condition )?after\s+([^.]+)")),
            "note": "",
        },
        "laser": {
            "na": laser_na,
            "pulseEnergy": _after(text, r"pulse energy\s+([^.]+)") if laser_na is False else None,
            "frequency": _after(text, r"frequency\s+([^.]+)") if laser_na is False else None,
            "stoneEffect": _after(text, r"stone effect\s+([^.]+)") if laser_na is False else None,
            "laserFiber": _after(text, r"laser fiber\s+([^.]+)") if laser_na is False else None,
            "note": "",
        },
        "drains": {
            "na": False if drains else (True if "no drain" in lower else None),
            "entries": drains,
        },
        "specimens": {
            "na": False if specimens else (True if "no specimen" in lower else None),
            "entries": specimens,
        },
    }


def _extract_sign_out(text: str, lower: str) -> Dict[str, Any]:
    def item(
        key: str,
        phrases: tuple[str, ...],
        *,
        response: Optional[str] = None,
        note: str = "",
    ) -> dict:
        template = next(t for t in SIGN_OUT_CHECKLIST_TEMPLATE if t["key"] == key)
        checked = True if any(p in lower for p in phrases) else None
        return {**template, "checked": checked, "response": response, "note": note}

    procedure_note = (
        _after(
            text,
            r"(?:name of (?:surgical )?(?:invasive )?procedure|surgical invasive procedure|procedure recorded(?: as)?)\s+([^.]+)",
        )
        or ""
    ).strip(" .,")
    if procedure_note:
        procedure_note = procedure_note[0].upper() + procedure_note[1:]

    counts_note = ""
    if "counts correct" in lower:
        counts_note = "Counts correct x2" if "x2" in lower else "Counts correct"
    elif "count discrepancy" in lower:
        counts_note = _after(text, r"count discrepancy\s+([^.]+)") or ""

    counts_response = None
    if any(p in lower for p in ("counts correct", "count correct", "needle counts", "sponge count")):
        counts_response = "YES"

    specimen_note = ""
    if "read aloud" in lower:
        specimen_note = _after(text, r"(two pathology labels read aloud|labels read aloud)") or ""
        if not specimen_note:
            specimen_note = _after(text, r"([^.]*read aloud[^.]*)") or ""
        if specimen_note and not specimen_note[0].isupper():
            specimen_note = specimen_note[0].upper() + specimen_note[1:]
    elif "specimen" in lower:
        specimen_note = _after(text, r"specimen[^.]*label(?:ed)?(?: as)?\s+([^.]+)") or ""

    specimen_response = "YES" if any(
        p in lower for p in ("specimen labeled", "labeling of specimens", "labels read aloud", "read aloud")
    ) else None

    equipment_response = None
    if re.search(r"equipment problems?\s+(no|none)\b", lower):
        equipment_response = "NO"
    elif re.search(r"equipment problems?\s+(yes|identified|noted)\b", lower):
        equipment_response = "YES"

    checklist = [
        item(
            "name_of_surgical_invasive_procedure",
            ("surgical invasive procedure", "procedure recorded", "name of procedure", "procedure name"),
            note=procedure_note,
        ),
        item(
            "instruments_sponge_needle_counts_completed",
            ("counts correct", "count correct", "needle counts", "sponge count", "instrument count"),
            response=counts_response,
            note=counts_note,
        ),
        item(
            "labeling_of_specimens",
            ("specimen labeled", "labeling of specimens", "labels read aloud", "read aloud"),
            response=specimen_response,
            note=specimen_note,
        ),
        item(
            "address_any_equipment_problems",
            ("equipment problems", "equipment problem"),
            response=equipment_response,
        ),
    ]
    return {"checklist": checklist}


def _extract_pre_eval(text: str, lower: str) -> Dict[str, Any]:
    return {
        "asa_class": _after(text, r"(ASA\s*[IVX1-6]+)"),
        "airway_assessment": _after(text, r"airway(?: assessment)?\s+([^.]+)"),
        "known_allergies": _list_after(text, r"allergies?\s+([^.]+)"),
        "current_medications": _list_after(text, r"medications?\s+([^.]+)"),
        "comorbidities": _list_after(text, r"comorbidit(?:y|ies)\s+([^.]+)"),
        "npo_status": _after(text, r"npo\s+([^.]+)"),
        "planned_anesthesia_type": _after(text, r"planned anesthesia\s+([^.]+)"),
        "planned_airway_technique": _after(text, r"planned airway\s+([^.]+)"),
        "risk_notes": _after(text, r"risk notes?\s+([^.]+)"),
        "consent_for_anesthesia": _flag(lower, "consent for anesthesia", "anesthesia consent"),
    }


def _extract_induction(text: str, lower: str) -> Dict[str, Any]:
    drug = _after(text, r"(?:giving|gave|induction with)\s+([a-zA-Z]+)")
    dose = _after(text, r"(\d+\s*mg)")
    attempt_match = re.search(r"intubation attempts?\s+(\d+)", lower)
    return {
        "induction_time": _after(text, r"induction(?: time)?\s+([0-9:]{4,5})"),
        "induction_agents": [{"drug": drug, "dose": dose, "time": _after(text, r"induction(?: time)?\s+([0-9:]{4,5})")}] if drug or dose else None,
        "airway_technique_used": _after(text, r"airway(?: technique)?(?: used)?\s+([^.]+)"),
        "intubation_attempts": int(attempt_match.group(1)) if attempt_match else None,
        "ventilation_mode": _after(text, r"ventilation(?: mode)?\s+([^.]+)"),
        "lines_placed": _list_after(text, r"lines? placed\s+([^.]+)"),
        "positioning": _after(text, r"position(?:ing)?\s+([^.]+)"),
        "intraoperative_events": _after(text, r"intraoperative events?\s+([^.]+)"),
        "notes": None,
    }


def _extract_observation(text: str, lower: str) -> Dict[str, Any]:
    hr = _after(text, r"(?:heart rate|hr)\s+(\d+)")
    bp = _after(text, r"(?:blood pressure|bp)\s+([\d/ ]+)")
    spo2 = _after(text, r"(?:spo2|saturations?)\s+(\d+\s*%?)")
    drug = _after(text, r"(?:giving|gave|administered)\s+([A-Za-z]+)")
    dose = _after(text, r"(\d+\s*(?:mg|mcg|µg))")
    fluids = None
    if "crystalloid" in lower or "saline" in lower or "lactated" in lower:
        fluids = [{"fluid": _after(text, r"(crystalloid|normal saline|lactated ringer'?s)") or "fluid", "volume_ml": _after(text, r"(\d+\s*ml)"), "time": None}]
    return {
        "vitals": [{"time": None, "hr": hr, "bp": bp, "spo2": spo2, "etco2": None, "temp": _after(text, r"temp(?:erature)?\s+([0-9.]+(?:\s*°?C)?)")}] if hr or bp or spo2 else None,
        "drugs_administered": [{"drug": drug, "dose": dose, "route": _after(text, r"route\s+([a-zA-Z]+)"), "time": None}] if drug or dose else None,
        "fluids_administered": fluids,
        "blood_products_administered": None,
        "estimated_blood_loss_ml": _after(text, r"(?:estimated blood loss|ebl)\s+([^.]+)"),
        "urine_output_ml": _after(text, r"urine output\s+([^.]+)"),
        "notes": None,
    }


def _extract_opnote(text: str, lower: str) -> Dict[str, Any]:
    del lower

    def _doctor_name(pattern: str) -> Optional[str]:
        value = _after(text, pattern)
        if not value:
            return None
        value = re.sub(r"^dr\.?\s*", "", value.strip(" .,"), flags=re.IGNORECASE).strip()
        if not value:
            return None
        return f"Dr. {value}"

    def _int_ml(pattern: str) -> Optional[int]:
        raw = _after(text, pattern)
        if not raw:
            return None
        digits = re.search(r"\d+", raw)
        return int(digits.group(0)) if digits else None

    anesthesia_raw = _after(text, r"type of anesthesia\s+([^.]+)") or _after(text, r"anesthesia type\s+([^.]+)")
    type_of_anesthesia = None
    if anesthesia_raw:
        type_of_anesthesia = anesthesia_raw.strip().split(".")[0].strip()
        if type_of_anesthesia:
            type_of_anesthesia = type_of_anesthesia[0].upper() + type_of_anesthesia[1:]

    note_match = re.search(
        r"operation note[:\s]+(.+?)(?:\.\s*complication|\.\s*estimated blood loss|$)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    operation_note = note_match.group(1).strip(" .") if note_match else None
    if not operation_note:
        fallback = re.search(
            r"(Under general anesthesia.+?)(?:\.\s*Complication|\.\s*Estimated blood loss|$)",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        operation_note = fallback.group(1).strip(" .") if fallback else None
    if operation_note:
        operation_note = re.sub(r"\s+", " ", operation_note).strip(" .")

    complication = _after(text, r"complication\s+([^.]+)")
    if complication:
        complication = complication.strip()
        if complication.lower() == "none":
            complication = "None"

    return {
        "operativeDetails": {
            "time": _after(text, r"(?:operative note )?time\s+(\d{1,2}:\d{2})"),
            "typeOfAnesthesia": type_of_anesthesia,
        },
        "operationStaff": {
            "mainSurgeon": _doctor_name(r"main surgeon\s+(dr\.?\s+[^.]+)"),
            "surgeonsAssistant": _doctor_name(r"surgeon'?s assistant\s+(dr\.?\s+[^.]+)"),
            "surgicalStartTime": _after(text, r"surgical start time\s+(\S+)"),
            "surgicalEndTime": _after(text, r"surgical end time\s+(\S+)"),
        },
        "operationNote": operation_note,
        "complication": complication,
        "estimatedBloodLossMl": _int_ml(r"estimated blood loss\s+(\d+)"),
    }


_STUB_EXTRACTORS = {
    "nursing_verification_of_marking_site": _extract_verification,
    "nursing_time_out": _extract_time_out,
    "nursing_intraoperative": _extract_intraoperative,
    "nursing_sign_out": _extract_sign_out,
    "anesthesia_pre_evaluation_plan": _extract_pre_eval,
    "anesthesia_induction_intraoperative": _extract_induction,
    "anesthesia_observation_drugs": _extract_observation,
    "operative_note": _extract_opnote,
}
