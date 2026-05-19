"""Deterministic extraction of clinically relevant risk signals."""
import re
from typing import Any, Dict, List, Optional

from app.agent.state import RiskSignal


def extract_risk_signals(patient_record: Dict[str, Any]) -> List[RiskSignal]:
    """Extract bounded deterministic risk signals from the patient record."""
    signals: List[RiskSignal] = []

    signals.extend(_extract_lab_signals(patient_record))
    signals.extend(_extract_vital_signals(patient_record))
    signals.extend(_extract_imaging_signals(patient_record))
    signals.extend(_extract_follow_up_signals(patient_record))
    signals.extend(_extract_medication_safety_signals(patient_record))
    signals.extend(_extract_note_signals(patient_record))

    return signals


def build_evidence_catalog(patient_record: Dict[str, Any]) -> List[str]:
    """Build a flattened evidence catalog from the patient record."""
    evidence: List[str] = []

    patient_id = patient_record.get("patient_id")
    if patient_id:
        evidence.append(f"Patient ID {patient_id}")

    demographics = patient_record.get("demographics") or {}
    age = demographics.get("age")
    sex = demographics.get("sex")
    if age is not None or sex:
        evidence.append(f"Demographics age {age} sex {sex}".strip())

    for diagnosis in patient_record.get("diagnoses") or []:
        name = diagnosis.get("name")
        date = diagnosis.get("date")
        if name:
            evidence.append(f"Diagnosis {name}" + (f" on {date}" if date else ""))

    for medication in patient_record.get("medications") or []:
        name = medication.get("name")
        status = medication.get("status")
        start_date = medication.get("start_date")
        end_date = medication.get("end_date")
        if name:
            line = f"Medication {name}"
            if status:
                line += f" status {status}"
            if start_date:
                line += f" start {start_date}"
            if end_date:
                line += f" end {end_date}"
            evidence.append(line)

    for allergy in patient_record.get("allergies") or []:
        name = allergy.get("name")
        if name:
            evidence.append(f"Allergy {name}")

    for lab in (patient_record.get("lab_results") or []) + (patient_record.get("historical_lab_results") or []):
        line = _format_measurement("Lab", lab.get("name"), lab.get("value"), lab.get("unit"), lab.get("date"))
        if lab.get("reference_range"):
            line += f" range {lab.get('reference_range')}"
        if lab.get("flag"):
            line += f" flag {lab.get('flag')}"
        if line:
            evidence.append(line)

    for vital in patient_record.get("vitals") or []:
        line = _format_measurement("Vital", vital.get("name"), vital.get("value"), vital.get("unit"), vital.get("date"))
        if line:
            evidence.append(line)

    for report in patient_record.get("imaging_reports") or []:
        report_type = report.get("type")
        text = report.get("text")
        date = report.get("date")
        if report_type and text:
            line = f"Imaging {report_type}"
            if date:
                line += f" on {date}"
            line += f": {text}"
            evidence.append(line)

    for note in patient_record.get("notes") or []:
        note_text = note.get("text")
        note_type = note.get("type")
        date = note.get("date")
        if note_text:
            line = "Note"
            if note_type:
                line += f" {note_type}"
            if date:
                line += f" on {date}"
            line += f": {note_text}"
            evidence.append(line)

    for follow_up in patient_record.get("discharge_follow_up") or []:
        specialty = follow_up.get("specialty")
        scheduled = follow_up.get("scheduled")
        if specialty is not None and scheduled is not None:
            evidence.append(f"Discharge follow-up {specialty} scheduled {scheduled}")

    return evidence


def _extract_lab_signals(patient_record: Dict[str, Any]) -> List[RiskSignal]:
    signals: List[RiskSignal] = []
    historical_by_name = {str(item.get("name", "")).lower(): item for item in patient_record.get("historical_lab_results") or []}

    for lab in patient_record.get("lab_results") or []:
        name = str(lab.get("name") or "").strip()
        if not name:
            continue

        flag = str(lab.get("flag") or "").strip().lower()
        value = str(lab.get("value") or "").strip()
        unit = str(lab.get("unit") or "").strip()
        date = str(lab.get("date") or "").strip()

        if flag in {"high", "low", "critical", "abnormal", "positive"}:
            severity = "critical" if flag == "critical" else "high"
            signals.append(
                RiskSignal(
                    signal_type="lab_abnormality",
                    category="lab_pattern_alert",
                    severity=severity,
                    summary=f"Abnormal lab result for {name}",
                    evidence=[_format_measurement("Lab", name, value, unit, date) + f" flag {flag}"],
                    recommended_specialty=_specialty_for_lab_name(name),
                )
            )

        historical = historical_by_name.get(name.lower())
        if historical:
            current_numeric = _extract_first_number(value)
            previous_numeric = _extract_first_number(historical.get("value"))
            if current_numeric is not None and previous_numeric is not None and current_numeric != previous_numeric:
                signals.append(
                    RiskSignal(
                        signal_type="lab_trend",
                        category="lab_pattern_alert",
                        severity=_trend_severity(name, current_numeric, previous_numeric),
                        summary=f"Possible change in {name} across serial results",
                        evidence=[
                            _format_measurement("Lab", name, value, unit, date),
                            _format_measurement(
                                "Lab",
                                historical.get("name"),
                                historical.get("value"),
                                historical.get("unit"),
                                historical.get("date"),
                            ),
                        ],
                        recommended_specialty=_specialty_for_lab_name(name),
                    )
                )

    return signals


def _extract_vital_signals(patient_record: Dict[str, Any]) -> List[RiskSignal]:
    signals: List[RiskSignal] = []

    for vital in patient_record.get("vitals") or []:
        name = str(vital.get("name") or "").strip().lower()
        value = str(vital.get("value") or "").strip()
        unit = str(vital.get("unit") or "").strip()
        date = str(vital.get("date") or "").strip()

        numeric_value = _extract_first_number(value)
        if not name or numeric_value is None:
            continue

        if "temp" in name and numeric_value >= 38.5:
            signals.append(
                RiskSignal(
                    signal_type="vital_instability",
                    category="urgent_escalation",
                    severity="high",
                    summary="Fever may indicate acute clinical deterioration",
                    evidence=[_format_measurement("Vital", vital.get("name"), value, unit, date)],
                    recommended_specialty="Infectious Disease",
                )
            )
        elif ("oxygen" in name or "spo2" in name or "saturation" in name) and numeric_value < 90:
            signals.append(
                RiskSignal(
                    signal_type="vital_instability",
                    category="urgent_escalation",
                    severity="critical",
                    summary="Low oxygen saturation may require urgent review",
                    evidence=[_format_measurement("Vital", vital.get("name"), value, unit, date)],
                    recommended_specialty="Pulmonology",
                )
            )
        elif ("blood_pressure" in name or name in {"bp", "blood pressure"}) and numeric_value < 90:
            signals.append(
                RiskSignal(
                    signal_type="vital_instability",
                    category="urgent_escalation",
                    severity="critical",
                    summary="Hypotension may indicate hemodynamic instability",
                    evidence=[_format_measurement("Vital", vital.get("name"), value, unit, date)],
                    recommended_specialty="Critical Care",
                )
            )
        elif ("heart_rate" in name or name in {"hr", "pulse"}) and (numeric_value > 130 or numeric_value < 40):
            signals.append(
                RiskSignal(
                    signal_type="vital_instability",
                    category="urgent_escalation",
                    severity="high",
                    summary="Marked heart rate abnormality may require urgent review",
                    evidence=[_format_measurement("Vital", vital.get("name"), value, unit, date)],
                    recommended_specialty="Cardiology",
                )
            )

    return signals


def _extract_imaging_signals(patient_record: Dict[str, Any]) -> List[RiskSignal]:
    signals: List[RiskSignal] = []
    keyword_map = {
        "hemorrhage": ("critical_clinical_alert", "critical", "Neurology"),
        "stroke": ("critical_clinical_alert", "critical", "Neurology"),
        "infarct": ("critical_clinical_alert", "critical", "Neurology"),
        "mass": ("imaging_follow_up", "high", "Oncology"),
        "effusion": ("imaging_follow_up", "medium", "Pulmonology"),
        "infiltrate": ("critical_clinical_alert", "high", "Pulmonology"),
        "fracture": ("critical_clinical_alert", "high", "Orthopedics"),
    }

    for report in patient_record.get("imaging_reports") or []:
        text = str(report.get("text") or "").strip()
        report_type = str(report.get("type") or "").strip()
        date = str(report.get("date") or "").strip()
        if not text:
            continue

        lowered = text.lower()
        for keyword, (category, severity, specialty) in keyword_map.items():
            if keyword in lowered:
                signals.append(
                    RiskSignal(
                        signal_type="imaging_finding",
                        category=category,
                        severity=severity,
                        summary=f"Imaging finding may require review for possible {specialty} involvement",
                        evidence=[f"{report_type} on {date}: {text}".strip()],
                        recommended_specialty=specialty,
                    )
                )
                break

    return signals


def _extract_follow_up_signals(patient_record: Dict[str, Any]) -> List[RiskSignal]:
    signals: List[RiskSignal] = []

    for follow_up in patient_record.get("discharge_follow_up") or []:
        specialty = str(follow_up.get("specialty") or "").strip()
        scheduled = follow_up.get("scheduled")
        if specialty and scheduled is False:
            signals.append(
                RiskSignal(
                    signal_type="follow_up_gap",
                    category="missing_follow_up",
                    severity="medium",
                    summary=f"Planned follow-up with {specialty} is not scheduled",
                    evidence=[f"Discharge follow-up {specialty} scheduled False"],
                    recommended_specialty=specialty,
                )
            )

    return signals


def _extract_medication_safety_signals(patient_record: Dict[str, Any]) -> List[RiskSignal]:
    signals: List[RiskSignal] = []
    active_medications = [
        med for med in patient_record.get("medications") or []
        if str(med.get("status") or "active").strip().lower() != "stopped"
    ]
    medication_names = [str(med.get("name") or "").lower() for med in active_medications]

    creatinine_abnormal = any(
        str(lab.get("name") or "").lower() == "creatinine"
        and str(lab.get("flag") or "").lower() in {"high", "critical", "abnormal"}
        for lab in patient_record.get("lab_results") or []
    )
    hemorrhage_mentioned = any(
        "hemorrhage" in str(report.get("text") or "").lower()
        for report in patient_record.get("imaging_reports") or []
    )

    if creatinine_abnormal and any(name in {"ibuprofen", "naproxen", "diclofenac", "ketorolac"} for name in medication_names):
        signals.append(
            RiskSignal(
                signal_type="medication_safety",
                category="medication_safety",
                severity="high",
                summary="NSAID exposure with abnormal creatinine may warrant medication safety review",
                evidence=[
                    "Active medication includes ibuprofen or another NSAID",
                    "Creatinine is flagged abnormal in current lab results",
                ],
                recommended_specialty="Nephrology",
            )
        )

    if hemorrhage_mentioned and any(name in {"warfarin", "apixaban", "rivaroxaban", "heparin"} for name in medication_names):
        signals.append(
            RiskSignal(
                signal_type="medication_safety",
                category="medication_safety",
                severity="critical",
                summary="Anticoagulant exposure with hemorrhagic imaging finding may require urgent medication review",
                evidence=[
                    "Active medication includes an anticoagulant",
                    "Imaging report mentions hemorrhage",
                ],
                recommended_specialty="Neurology",
            )
        )

    return signals


def _extract_note_signals(patient_record: Dict[str, Any]) -> List[RiskSignal]:
    signals: List[RiskSignal] = []
    note_keywords = {
        "confused": ("urgent_escalation", "high", "Neurology"),
        "worsened": ("critical_clinical_alert", "high", None),
        "febrile": ("urgent_escalation", "high", "Infectious Disease"),
        "shortness of breath": ("urgent_escalation", "high", "Pulmonology"),
    }

    for note in patient_record.get("notes") or []:
        text = str(note.get("text") or "").strip()
        date = str(note.get("date") or "").strip()
        note_type = str(note.get("type") or "").strip()
        if not text:
            continue

        lowered = text.lower()
        for keyword, (category, severity, specialty) in note_keywords.items():
            if keyword in lowered:
                signals.append(
                    RiskSignal(
                        signal_type="note_pattern",
                        category=category,
                        severity=severity,
                        summary=f"Clinical note describes {keyword}",
                        evidence=[f"Note {note_type} on {date}: {text}".strip()],
                        recommended_specialty=specialty,
                    )
                )
                break

    return signals


def _format_measurement(prefix: str, name: Any, value: Any, unit: Any, date: Any) -> str:
    label = str(name or "").strip()
    raw_value = str(value or "").strip()
    raw_unit = str(unit or "").strip()
    raw_date = str(date or "").strip()

    parts = [prefix]
    if label:
        parts.append(label)
    if raw_value:
        parts.append(raw_value)
    if raw_unit:
        parts.append(raw_unit)
    line = " ".join(parts).strip()
    if raw_date:
        line += f" on {raw_date}"
    return line


def _extract_first_number(value: Any) -> Optional[float]:
    if value is None:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", str(value))
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _trend_severity(name: str, current_value: float, previous_value: float) -> str:
    difference = abs(current_value - previous_value)
    if previous_value == 0:
        return "high"
    change_ratio = difference / abs(previous_value)
    if "creatinine" in name.lower() and change_ratio >= 0.5:
        return "high"
    if change_ratio >= 1.0:
        return "high"
    if change_ratio >= 0.25:
        return "medium"
    return "low"


def _specialty_for_lab_name(name: str) -> Optional[str]:
    lowered = name.lower()
    if lowered in {"creatinine", "bun", "egfr"}:
        return "Nephrology"
    if lowered in {"troponin", "bnp"}:
        return "Cardiology"
    if lowered in {"wbc", "crp", "procalcitonin"}:
        return "Infectious Disease"
    return None
