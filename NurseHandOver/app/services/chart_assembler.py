"""
chart_assembler.py
------------------
Builds a current-status snapshot from a raw Patient chart.

Callers (the agent / EMR) may send full allergy/warning lists, vital history,
and procedures in any status. The handover only needs:

- allergies and warnings that are not resolved
- the latest reading per vital-sign type
- operations/procedures that are still pending or scheduled
"""

from datetime import datetime, timezone
from typing import Iterable, List, Optional, Sequence

from app.models.schemas import (
    Allergy,
    ClinicalWarning,
    Patient,
    PatientCurrentStatus,
    PendingProcedure,
    VitalSignReading,
    Vitals,
)

_RESOLVED_STATUSES = frozenset({
    "resolved",
    "inactive",
    "cleared",
    "closed",
    "complete",
    "completed",
})

_PENDING_PROCEDURE_STATUSES = frozenset({
    "pending",
    "scheduled",
    "planned",
    "booked",
    "ordered",
    "not completed",
    "not_completed",
})

_COMPLETED_PROCEDURE_STATUSES = frozenset({
    "completed",
    "complete",
    "done",
    "performed",
    "cancelled",
    "canceled",
})

_VITAL_TYPE_ALIASES = {
    "hr": "hr",
    "heart_rate": "hr",
    "heart rate": "hr",
    "pulse": "hr",
    "pulse_rate": "hr",
    "bp": "bp",
    "blood_pressure": "bp",
    "blood pressure": "bp",
    "temp": "temp",
    "temperature": "temp",
    "temperature_c": "temp",
    "rr": "rr",
    "respiratory_rate": "rr",
    "respiratory rate": "rr",
    "spo2": "spo2",
    "spo2_pct": "spo2",
    "o2sat": "spo2",
    "o2_sat": "spo2",
    "oxygen_saturation": "spo2",
    "oxygen saturation": "spo2",
}


def _normalize_status(status: Optional[str]) -> str:
    return (status or "").strip().lower()


def is_resolved(status: Optional[str] = None, resolved: Optional[bool] = None) -> bool:
    """True when an allergy/warning should be excluded from the handover."""
    if resolved is True:
        return True
    if resolved is False:
        return False
    return _normalize_status(status) in _RESOLVED_STATUSES


def active_allergies(items: Sequence[Allergy]) -> List[Allergy]:
    return [item for item in items if not is_resolved(item.status, item.resolved)]


def active_warnings(items: Sequence[ClinicalWarning]) -> List[ClinicalWarning]:
    return [item for item in items if not is_resolved(item.status, item.resolved)]


def pending_procedures(items: Sequence[PendingProcedure]) -> List[PendingProcedure]:
    """Keep scheduled/pending procedures; drop completed/cancelled ones."""
    kept: List[PendingProcedure] = []
    for item in items:
        status = _normalize_status(item.status)
        if status in _COMPLETED_PROCEDURE_STATUSES:
            continue
        if not status or status in _PENDING_PROCEDURE_STATUSES:
            kept.append(item)
            continue
        if "complete" not in status:
            kept.append(item)
    return kept


def normalize_vital_type(vital_type: str) -> str:
    key = (vital_type or "").strip().lower()
    return _VITAL_TYPE_ALIASES.get(key, key or "unknown")


def _parse_recorded_at(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _reading_sort_key(index: int, reading: VitalSignReading) -> tuple:
    parsed = _parse_recorded_at(reading.recorded_at)
    if parsed is not None:
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return (1, parsed.timestamp(), index)
    if reading.recorded_at:
        return (0, reading.recorded_at, index)
    return (0, "", index)


def latest_vital_signs(
    readings: Sequence[VitalSignReading],
    compact: Optional[Vitals] = None,
) -> List[VitalSignReading]:
    """One reading per vital type — the most recent. Compact `vitals` are included then overlaid."""
    combined: List[VitalSignReading] = []
    if compact is not None:
        combined.extend(_readings_from_compact(compact))
    combined.extend(readings)

    latest: dict[str, tuple[tuple, VitalSignReading]] = {}
    for index, reading in enumerate(combined):
        vital_type = normalize_vital_type(reading.type)
        normalized = reading.model_copy(update={"type": vital_type})
        key = _reading_sort_key(index, normalized)
        previous = latest.get(vital_type)
        if previous is None or key >= previous[0]:
            latest[vital_type] = (key, normalized)

    ordered = [item[1] for item in latest.values()]
    ordered.sort(key=lambda r: r.type)
    return ordered


def _readings_from_compact(vitals: Vitals) -> List[VitalSignReading]:
    mapping = (
        ("hr", vitals.hr, "bpm"),
        ("bp", vitals.bp, "mmHg"),
        ("temp", vitals.temp, "°C"),
        ("rr", vitals.rr, "/min"),
        ("spo2", vitals.spo2, "%"),
    )
    readings: List[VitalSignReading] = []
    for vital_type, value, unit in mapping:
        if value is None or value == "":
            continue
        readings.append(
            VitalSignReading(
                type=vital_type,
                value=value,
                unit=unit,
                recorded_at=vitals.last_updated,
            )
        )
    return readings


def compact_vitals_from_readings(readings: Iterable[VitalSignReading]) -> Vitals:
    """Map latest typed readings back onto the compact Vitals object for the prompt."""
    by_type = {normalize_vital_type(r.type): r for r in readings}
    last_updated = None
    timestamps = [r.recorded_at for r in readings if r.recorded_at]
    if timestamps:
        last_updated = max(timestamps)

    def _int(reading: Optional[VitalSignReading]) -> Optional[int]:
        if reading is None:
            return None
        try:
            return int(float(reading.value))
        except (TypeError, ValueError):
            return None

    def _float(reading: Optional[VitalSignReading]) -> Optional[float]:
        if reading is None:
            return None
        try:
            return float(reading.value)
        except (TypeError, ValueError):
            return None

    def _str(reading: Optional[VitalSignReading]) -> Optional[str]:
        if reading is None:
            return None
        return str(reading.value)

    return Vitals(
        hr=_int(by_type.get("hr")),
        bp=_str(by_type.get("bp")),
        temp=_float(by_type.get("temp")),
        rr=_int(by_type.get("rr")),
        spo2=_int(by_type.get("spo2")),
        last_updated=last_updated,
    )


def assemble_current_status(
    patient: Patient,
    generated_at: Optional[datetime] = None,
) -> PatientCurrentStatus:
    stamp = generated_at or datetime.now(timezone.utc)
    vitals = latest_vital_signs(patient.vital_signs, compact=patient.vitals)
    return PatientCurrentStatus(
        patient_id=patient.patient_id,
        diagnosis=patient.diagnosis,
        past_medical_history=patient.past_medical_history,
        hospital_course=patient.hospital_course,
        allergies=active_allergies(patient.allergies),
        warnings=active_warnings(patient.warnings),
        vital_signs=vitals,
        pending_procedures=pending_procedures(patient.pending_procedures),
        generated_at=stamp,
    )
