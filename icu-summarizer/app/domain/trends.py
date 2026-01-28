"""Trend Engine - Compute trends and detect notable changes (deterministic)"""
from datetime import datetime
from typing import List, Optional, Dict, Any
from decimal import Decimal, InvalidOperation

from app.domain.input_models import (
    FlowsheetEntry, MedicationEntry, LabEntry, EventEntry, LineTubeInfo, ICURequestPayload
)
from app.domain.clinical_models import (
    ClinicalSummary, VitalTrend, InfusionStatus, IOStatus, SystemSummary
)
from app.domain.normalization import ConceptNormalizer
from app.utils.time_utils import is_within_window


def safe_float(value: str) -> Optional[float]:
    """Safely convert string to float, return None if invalid"""
    if not value or not isinstance(value, str):
        return None
    try:
        # Remove common non-numeric characters
        cleaned = value.strip().replace(',', '').replace('%', '')
        return float(cleaned)
    except (ValueError, InvalidOperation):
        return None


def detect_notable_change(concept: str, last: Optional[float], min_val: Optional[float], 
                         max_val: Optional[float], unit: Optional[str]) -> List[str]:
    """Detect notable changes in vital signs"""
    changes = []
    
    if last is None or min_val is None or max_val is None:
        return changes
    
    # Define thresholds for notable changes
    thresholds = {
        'heart_rate': {'significant_delta': 20, 'critical_low': 50, 'critical_high': 120},
        'mean_arterial_pressure': {'significant_delta': 15, 'critical_low': 60, 'critical_high': 100},
        'fio2': {'significant_delta': 10, 'critical_low': 21, 'critical_high': 100},
        'oxygen_saturation': {'significant_delta': 5, 'critical_low': 90, 'critical_high': 100},
        'respiratory_rate': {'significant_delta': 5, 'critical_low': 12, 'critical_high': 30},
        'temperature': {'significant_delta': 1.0, 'critical_low': 36.0, 'critical_high': 38.5},
    }
    
    threshold = thresholds.get(concept)
    if not threshold:
        return changes
    
    delta = max_val - min_val
    if delta >= threshold['significant_delta']:
        changes.append(f"{concept.replace('_', ' ').title()} varied by {delta:.1f} {unit or ''} (range: {min_val:.1f}-{max_val:.1f})")
    
    if last <= threshold.get('critical_low', float('-inf')):
        changes.append(f"{concept.replace('_', ' ').title()} critically low: {last:.1f} {unit or ''}")
    elif last >= threshold.get('critical_high', float('inf')):
        changes.append(f"{concept.replace('_', ' ').title()} critically high: {last:.1f} {unit or ''}")
    
    return changes


def compute_vital_trend(entries: List[FlowsheetEntry], concept: str, 
                       normalizer: ConceptNormalizer, time_window_start: datetime,
                       time_window_end: datetime) -> Optional[VitalTrend]:
    """Compute trend for a vital sign"""
    # Filter and normalize entries
    relevant_entries = []
    for entry in entries:
        if not is_within_window(entry.timestamp, time_window_start, time_window_end):
            continue
        
        normalized = normalizer.normalize(entry.item_name, entry.item_code)
        if normalized == concept:
            relevant_entries.append(entry)
    
    if not relevant_entries:
        return None
    
    # Extract numeric values
    values = []
    unit = None
    for entry in relevant_entries:
        val = safe_float(entry.value)
        if val is not None:
            values.append(val)
            if not unit and entry.unit:
                unit = entry.unit
    
    if not values:
        return None
    
    # Sort by timestamp to get last value
    sorted_entries = sorted(relevant_entries, key=lambda e: e.timestamp)
    last_entry = sorted_entries[-1]
    last_val = safe_float(last_entry.value)
    
    min_val = min(values)
    max_val = max(values)
    
    # Detect notable changes
    notable_changes = detect_notable_change(concept, last_val, min_val, max_val, unit)
    
    return VitalTrend(
        last=last_val,
        min=min_val,
        max=max_val,
        unit=unit,
        notable_changes=notable_changes
    )


def compute_infusions(meds: List[MedicationEntry], time_window_start: datetime,
                     time_window_end: datetime) -> List[InfusionStatus]:
    """Compute active infusions and their rates"""
    infusions = []
    
    # Group by medication name
    infusion_groups: Dict[str, List[MedicationEntry]] = {}
    for med in meds:
        if not med.is_infusion:
            continue
        if not is_within_window(med.timestamp, time_window_start, time_window_end):
            continue
        
        if med.med_name not in infusion_groups:
            infusion_groups[med.med_name] = []
        infusion_groups[med.med_name].append(med)
    
    # Process each infusion
    for med_name, entries in infusion_groups.items():
        # Sort by timestamp
        sorted_entries = sorted(entries, key=lambda e: e.timestamp)
        
        # Get current (most recent) rate
        current_entry = sorted_entries[-1]
        current_rate = current_entry.rate
        rate_unit = current_entry.rate_unit
        
        # Find max rate
        max_rate = None
        for entry in sorted_entries:
            if entry.rate:
                rate_val = safe_float(entry.rate)
                if rate_val is not None:
                    if max_rate is None or rate_val > max_rate:
                        max_rate = rate_val
                        max_rate_str = entry.rate
        
        infusions.append(InfusionStatus(
            med_name=med_name,
            current_rate=current_rate,
            max_rate=max_rate_str if max_rate is not None else None,
            rate_unit=rate_unit,
            dose=current_entry.dose,
            dose_unit=current_entry.dose_unit
        ))
    
    return infusions


def compute_io_status(flowsheet: List[FlowsheetEntry], normalizer: ConceptNormalizer,
                     time_window_start: datetime, time_window_end: datetime) -> Optional[IOStatus]:
    """Compute input/output status"""
    # Look for urine output entries
    uop_entries = []
    for entry in flowsheet:
        if not is_within_window(entry.timestamp, time_window_start, time_window_end):
            continue
        
        normalized = normalizer.normalize(entry.item_name, entry.item_code)
        if normalized in ['urine_output', 'uop']:
            uop_entries.append(entry)
    
    if not uop_entries:
        return None
    
    # Sum urine output
    total_uop = 0.0
    unit = None
    for entry in uop_entries:
        val = safe_float(entry.value)
        if val is not None:
            total_uop += val
        if not unit and entry.unit:
            unit = entry.unit
    
    # TODO: Compute net balance if input data available
    # For now, just return UOP total
    
    return IOStatus(
        urine_output_total=total_uop if total_uop > 0 else None,
        net_balance=None,  # Would need input data
        unit=unit or "mL"
    )


def build_clinical_summary(payload: ICURequestPayload, 
                          normalizer: ConceptNormalizer) -> ClinicalSummary:
    """
    Build structured clinical summary from request payload.
    This is the main entry point for trend analysis.
    """
    time_start = payload.time_window.start
    time_end = payload.time_window.end
    
    # Compute vital trends
    heart_rate = compute_vital_trend(
        payload.flowsheet, 'heart_rate', normalizer, time_start, time_end
    )
    mean_arterial_pressure = compute_vital_trend(
        payload.flowsheet, 'mean_arterial_pressure', normalizer, time_start, time_end
    )
    blood_pressure_systolic = compute_vital_trend(
        payload.flowsheet, 'blood_pressure_systolic', normalizer, time_start, time_end
    )
    blood_pressure_diastolic = compute_vital_trend(
        payload.flowsheet, 'blood_pressure_diastolic', normalizer, time_start, time_end
    )
    temperature = compute_vital_trend(
        payload.flowsheet, 'temperature', normalizer, time_start, time_end
    )
    respiratory_rate = compute_vital_trend(
        payload.flowsheet, 'respiratory_rate', normalizer, time_start, time_end
    )
    oxygen_saturation = compute_vital_trend(
        payload.flowsheet, 'oxygen_saturation', normalizer, time_start, time_end
    )
    fio2 = compute_vital_trend(
        payload.flowsheet, 'fio2', normalizer, time_start, time_end
    )
    peep = compute_vital_trend(
        payload.flowsheet, 'peep', normalizer, time_start, time_end
    )
    tidal_volume = compute_vital_trend(
        payload.flowsheet, 'tidal_volume', normalizer, time_start, time_end
    )
    
    # Compute infusions
    active_infusions = compute_infusions(payload.meds, time_start, time_end)
    
    # Compute I/O
    io_status = compute_io_status(payload.flowsheet, normalizer, time_start, time_end)
    
    # Recent labs (last 3)
    recent_labs = []
    sorted_labs = sorted(payload.labs, key=lambda l: l.timestamp, reverse=True)
    for lab in sorted_labs[:3]:
        if is_within_window(lab.timestamp, time_start, time_end):
            recent_labs.append({
                'lab_name': lab.lab_name,
                'value': lab.value,
                'unit': lab.unit,
                'ref_range': lab.ref_range,
                'timestamp': lab.timestamp.isoformat()
            })
    
    # Recent events (last 5)
    recent_events = []
    sorted_events = sorted(payload.events, key=lambda e: e.timestamp, reverse=True)
    for event in sorted_events[:5]:
        if is_within_window(event.timestamp, time_start, time_end):
            recent_events.append({
                'type': event.type,
                'description': event.description,
                'timestamp': event.timestamp.isoformat()
            })
    
    # Lines and tubes
    lines_tubes_data = []
    for lt in payload.lines_tubes:
        lines_tubes_data.append({
            'name': lt.name,
            'status': lt.status,
            'inserted_time': lt.inserted_time.isoformat() if lt.inserted_time else None
        })
    
    return ClinicalSummary(
        patient_id=payload.patient.id,
        time_window_start=time_start,
        time_window_end=time_end,
        heart_rate=heart_rate,
        blood_pressure_systolic=blood_pressure_systolic,
        blood_pressure_diastolic=blood_pressure_diastolic,
        mean_arterial_pressure=mean_arterial_pressure,
        temperature=temperature,
        respiratory_rate=respiratory_rate,
        oxygen_saturation=oxygen_saturation,
        fio2=fio2,
        peep=peep,
        tidal_volume=tidal_volume,
        active_infusions=active_infusions,
        io_status=io_status,
        systems=SystemSummary(),  # Will be populated by LLM
        recent_labs=recent_labs,
        recent_events=recent_events,
        lines_tubes=lines_tubes_data,
        diagnoses=payload.diagnoses,
        code_status=payload.code_status
    )
