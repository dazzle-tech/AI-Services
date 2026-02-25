"""Use case for generating ICU summaries"""
from typing import Dict, Any, List
from app.domain.input_models import ICURequestPayload
from app.domain.clinical_models import ClinicalSummary
from app.domain.normalization import ConceptNormalizer, load_mappings_from_yaml
from app.domain.trends import build_clinical_summary
from app.infrastructure.openai_client import OpenAIClient
from app.infrastructure.llm_prompt import (
    build_summary_prompt, build_structured_note_prompt, NOTE_JSON_SCHEMA
)
from app.utils.errors import ExternalServiceError, ValidationError
from app.utils.time_utils import validate_timestamps_in_window
from pathlib import Path


class SummarizeUseCase:
    """Use case for generating ICU daily summaries"""
    
    def __init__(self, normalizer: ConceptNormalizer, openai_client: OpenAIClient):
        """
        Initialize use case.
        
        Args:
            normalizer: Concept normalizer for flowsheet mapping
            openai_client: OpenAI client for LLM generation
        """
        self.normalizer = normalizer
        self.openai_client = openai_client
    
    def execute(self, payload: ICURequestPayload) -> Dict[str, Any]:
        """
        Execute the summarize use case.
        
        Args:
            payload: ICU request payload
            
        Returns:
            Dictionary with note_markdown, note_json, warnings, source_counts
            
        Raises:
            ValidationError: If validation fails
            ExternalServiceError: If OpenAI call fails
        """
        # Validate time window
        if payload.time_window.end <= payload.time_window.start:
            raise ValidationError("Time window end must be after start")
        
        # Validate and filter timestamps
        warnings: List[str] = []
        
        valid_flowsheet, flow_warnings = validate_timestamps_in_window(
            payload.flowsheet, payload.time_window.start, payload.time_window.end
        )
        warnings.extend(flow_warnings)
        
        valid_meds, med_warnings = validate_timestamps_in_window(
            payload.meds, payload.time_window.start, payload.time_window.end
        )
        warnings.extend(med_warnings)
        
        valid_labs, lab_warnings = validate_timestamps_in_window(
            payload.labs, payload.time_window.start, payload.time_window.end
        )
        warnings.extend(lab_warnings)
        
        valid_events, event_warnings = validate_timestamps_in_window(
            payload.events, payload.time_window.start, payload.time_window.end
        )
        warnings.extend(event_warnings)
        
        # Create modified payload with validated entries
        validated_payload = ICURequestPayload(
            patient=payload.patient,
            encounter=payload.encounter,
            time_window=payload.time_window,
            flowsheet=valid_flowsheet,
            meds=valid_meds,
            labs=valid_labs,
            events=valid_events,
            lines_tubes=payload.lines_tubes,
            diagnoses=payload.diagnoses,
            code_status=payload.code_status
        )
        
        # Build clinical summary (domain layer)
        clinical_summary = build_clinical_summary(validated_payload, self.normalizer)
        
        # Detect impossible values and add warnings
        data_quality_warnings = self._validate_data_quality(clinical_summary)
        warnings.extend(data_quality_warnings)
        
        # Generate markdown note (LLM)
        try:
            markdown_prompt = build_summary_prompt(clinical_summary)
            note_markdown = self.openai_client.generate_text_completion(markdown_prompt)
        except ExternalServiceError as e:
            raise ExternalServiceError(
                f"Failed to generate markdown note: {str(e)}",
                service="OPENAI"
            )
        
        # Generate structured JSON note (LLM)
        try:
            json_prompt = build_structured_note_prompt(clinical_summary)
            note_json = self.openai_client.generate_structured_completion(
                json_prompt, NOTE_JSON_SCHEMA
            )
            
            # Add LLM-generated warnings if any
            if isinstance(note_json, dict) and 'warnings' in note_json:
                llm_warnings = note_json.pop('warnings', [])
                if isinstance(llm_warnings, list):
                    warnings.extend(llm_warnings)
        except ExternalServiceError as e:
            raise ExternalServiceError(
                f"Failed to generate structured note: {str(e)}",
                service="OPENAI"
            )
        
        # Source counts
        source_counts = {
            "flowsheet": len(validated_payload.flowsheet),
            "meds": len(validated_payload.meds),
            "labs": len(validated_payload.labs),
            "events": len(validated_payload.events)
        }
        
        return {
            "note_markdown": note_markdown,
            "note_json": note_json,
            "warnings": warnings,
            "source_counts": source_counts
        }
    
    def _validate_data_quality(self, clinical_summary: ClinicalSummary) -> List[str]:
        """Validate data quality and detect impossible values"""
        warnings = []
        
        # Check heart rate
        if clinical_summary.heart_rate:
            hr = clinical_summary.heart_rate.last
            if hr is not None and (hr < 0 or hr > 300):
                warnings.append(f"Impossible heart rate value: {hr}")
        
        # Check MAP
        if clinical_summary.mean_arterial_pressure:
            map_val = clinical_summary.mean_arterial_pressure.last
            if map_val is not None and (map_val < 0 or map_val > 300):
                warnings.append(f"Impossible MAP value: {map_val}")
        
        # Check temperature
        if clinical_summary.temperature:
            temp = clinical_summary.temperature.last
            if temp is not None and (temp < 30 or temp > 45):
                warnings.append(f"Impossible temperature value: {temp}")
        
        # Check SpO2
        if clinical_summary.oxygen_saturation:
            spo2 = clinical_summary.oxygen_saturation.last
            if spo2 is not None and (spo2 < 0 or spo2 > 100):
                warnings.append(f"Impossible SpO2 value: {spo2}")
        
        # Check FiO2
        if clinical_summary.fio2:
            fio2 = clinical_summary.fio2.last
            if fio2 is not None and (fio2 < 0 or fio2 > 100):
                warnings.append(f"Impossible FiO2 value: {fio2}")
        
        return warnings
