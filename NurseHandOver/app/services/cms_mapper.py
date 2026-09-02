"""
cms_mapper.py
-------------
Maps the hospital CMS generate payload onto the internal Patient / GenerateSummaryRequest
models used by the SBAR pipeline.
"""

from typing import Any, List, Optional

from app.models.schemas import (
    Allergy,
    ClinicalWarning,
    CmsHandoverRequest,
    GenerateSummaryRequest,
    Patient,
    PendingProcedure,
    VitalSignReading,
)

_VITAL_FIELD_MAP = {
    "pulse_rate": ("hr", "bpm"),
    "heart_rate": ("hr", "bpm"),
    "hr": ("hr", "bpm"),
    "respiratory_rate": ("rr", "/min"),
    "rr": ("rr", "/min"),
    "spo2_pct": ("spo2", "%"),
    "spo2": ("spo2", "%"),
    "temperature_c": ("temp", "°C"),
    "temp": ("temp", "°C"),
    "pain_score": ("pain", None),
    "pain": ("pain", None),
}


def parse_generate_payload(payload: Any) -> GenerateSummaryRequest:
    """Accept the CMS body (`patient_data`) or a single-patient legacy body."""
    if not isinstance(payload, dict):
        return GenerateSummaryRequest.model_validate(payload)
    if "patient_data" in payload:
        cms = CmsHandoverRequest.model_validate(payload)
        return cms_to_generate_request(cms)
    return GenerateSummaryRequest.model_validate(payload)


def cms_to_generate_request(cms: CmsHandoverRequest) -> GenerateSummaryRequest:
    data = cms.patient_data
    patient_id = data.patient_id or "unspecified"
    patient = Patient(
        patient_id=patient_id,
        name=data.name or "not recorded",
        diagnosis=_format_diagnoses(data.diagnosis),
        past_medical_history=_format_past_medical_history(data.past_medical_history),
        hospital_course=data.last_hospital_course,
        allergies=_map_allergies(data.allergies),
        warnings=_map_warnings(data.warnings),
        vital_signs=_map_vital_signs(data.vital_signs),
        pending_procedures=_map_operations(data.pending_operations),
    )
    return GenerateSummaryRequest(
        handover_nurse=cms.handover_nurse,
        patient=patient,
    )


def _map_allergies(items) -> List[Allergy]:
    mapped: List[Allergy] = []
    for item in items or []:
        resolved = item.resolved if item.resolved is not None else item.is_resolved
        mapped.append(
            Allergy(
                name=item.allergy_description,
                category=item.allergy_type_description,
                status=item.status,
                resolved=resolved,
            )
        )
    return mapped


def _map_warnings(items) -> List[ClinicalWarning]:
    mapped: List[ClinicalWarning] = []
    for item in items or []:
        resolved = item.resolved if item.resolved is not None else item.is_resolved
        mapped.append(
            ClinicalWarning(
                text=item.virus_description,
                category=item.type,
                status=item.status,
                resolved=resolved,
            )
        )
    return mapped


def _map_operations(items) -> List[PendingProcedure]:
    return [
        PendingProcedure(
            name=item.operation_name,
            status=item.status or "pending",
            scheduled_at=item.requested_date,
            notes=item.notes,
        )
        for item in items or []
    ]


def _format_diagnoses(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    lines = []
    for item in value:
        desc = (item.diagnosis_description or "").strip()
        code = (item.diagnosis_code or "").strip()
        kind = (item.diagnosis_type or "").strip()
        if not desc and not code:
            continue
        label = desc or code
        if code and desc:
            label = f"{desc} ({code})"
        if kind:
            label = f"{kind}: {label}"
        lines.append(label)
    return "; ".join(lines) if lines else None


def _format_past_medical_history(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    lines = []
    for item in value:
        kind = (item.record_type or "").strip()
        desc = (item.record_description or "").strip()
        if not kind and not desc:
            continue
        lines.append(f"{kind}: {desc}" if kind and desc else (kind or desc))
    return "\n".join(lines) if lines else None


def _observation_value(entry: Any) -> tuple[Any, Optional[str]]:
    if isinstance(entry, dict):
        value = entry.get("value", entry.get("reading", entry.get("result")))
        recorded_at = entry.get("recorded_at") or entry.get("timestamp") or entry.get("observed_at")
        return value, recorded_at
    return entry, None


def _latest_observation(raw: Any) -> tuple[Any, Optional[str]]:
    if not isinstance(raw, list):
        return _observation_value(raw)
    best: tuple | None = None
    for index, entry in enumerate(raw):
        value, recorded_at = _observation_value(entry)
        if value in (None, ""):
            continue
        key = (1, recorded_at, index) if recorded_at else (0, "", index)
        if best is None or key >= best[0]:
            best = (key, value, recorded_at)
    if best is None:
        return None, None
    return best[1], best[2]


def _map_vital_signs(raw: Any) -> List[VitalSignReading]:
    if raw is None:
        return []
    if isinstance(raw, list):
        readings: List[VitalSignReading] = []
        for item in raw:
            if isinstance(item, dict):
                vital_type = item.get("type") or item.get("name")
                value = item.get("value")
                if not vital_type or value in (None, ""):
                    continue
                readings.append(
                    VitalSignReading(
                        type=str(vital_type),
                        value=value,
                        unit=item.get("unit"),
                        recorded_at=item.get("recorded_at") or item.get("timestamp"),
                    )
                )
        return readings
    if not isinstance(raw, dict):
        return []

    readings = []
    systolic, systolic_at = _latest_observation(raw.get("bp_systolic"))
    diastolic, diastolic_at = _latest_observation(raw.get("bp_diastolic"))
    if systolic not in (None, "") and diastolic not in (None, ""):
        readings.append(
            VitalSignReading(
                type="bp",
                value=f"{systolic}/{diastolic}",
                unit="mmHg",
                recorded_at=systolic_at or diastolic_at,
            )
        )
    elif systolic not in (None, ""):
        readings.append(VitalSignReading(type="bp_systolic", value=systolic, unit="mmHg", recorded_at=systolic_at))
    elif diastolic not in (None, ""):
        readings.append(VitalSignReading(type="bp_diastolic", value=diastolic, unit="mmHg", recorded_at=diastolic_at))

    for source_key, (vital_type, unit) in _VITAL_FIELD_MAP.items():
        if source_key not in raw:
            continue
        value, recorded_at = _latest_observation(raw.get(source_key))
        if value in (None, ""):
            continue
        readings.append(
            VitalSignReading(type=vital_type, value=value, unit=unit, recorded_at=recorded_at)
        )
    return readings
