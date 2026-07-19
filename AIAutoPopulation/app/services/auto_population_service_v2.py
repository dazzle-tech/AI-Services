"""Service layer for auto-population task - Version 2 (Clean API Contract)."""
import logging
from typing import Dict, Any
from datetime import datetime

from app.models.schemas_v2 import (
    AutoPopulationRequestV2,
    AutoPopulationResponseV2,
    Outputs,
    Quality,
    Trace,
    Metadata,
    ContradictionFlagV2,
    SourceTraceV2
)
from app.models.schemas import (
    StructuredFields,
    UncertaintyFlag,
    Warning
)
from app.services.auto_population_service import AutoPopulationService
from app.services.spell_correction import correct_text
from app.core.config import settings

logger = logging.getLogger(__name__)


class AutoPopulationServiceV2:
    """Service for handling auto-population requests (Version 2)."""
    
    def __init__(self):
        """Initialize service with V1 service for core processing."""
        self.v1_service = AutoPopulationService()
    
    def process_request(self, request: AutoPopulationRequestV2) -> AutoPopulationResponseV2:
        """
        Process an auto-population request (V2 format).
        
        Args:
            request: Auto-population request in V2 format
            
        Returns:
            Auto-population response in V2 format
        """
        try:
            logger.info(f"Processing V2 request {request.request_id}")
            
            # Convert V2 request to V1 format for processing
            from app.models.schemas import AutoPopulationRequest
            
            expected_fields = request.get_expected_fields()
            vitals_only = (
                not request.requested_outputs.include_structured_fields and 
                request.requested_outputs.include_vitals and
                len(expected_fields) == 1 and 
                "vitals" in expected_fields
            )
            
            # Apply spell correction to user text before processing
            corrected_user_text = correct_text(request.inputs.user_text, vitals_only=vitals_only)
            logger.debug(f"Applied spell correction to user text (original length: {len(request.inputs.user_text)}, corrected length: {len(corrected_user_text)})")
            
            # Optimize patient_data for vitals-only requests (only send vitals for comparison)
            patient_data = request.inputs.onsite.get_patient_data_dict()
            if vitals_only:
                # Only send vitals from patient record for comparison
                patient_data = {
                    "vitals": patient_data.get("vitals", {})
                }
            
            v1_request = AutoPopulationRequest(
                request_id=request.request_id,
                input_language=request.languages.input,
                output_language=request.languages.output,
                user_text=corrected_user_text,  # Use spell-corrected text
                patient_data=patient_data,
                expected_output=expected_fields
            )
            
            # Process using V1 service with vitals_only flag
            v1_response = self.v1_service.process_request(v1_request, vitals_only=vitals_only)
            
            # Convert V1 response to V2 format
            return self._convert_v1_to_v2_response(v1_response, request)
            
        except Exception as e:
            logger.error(f"Error processing V2 request {request.request_id}: {e}")
            # Even on error, try to extract vitals if requested (fallback extraction)
            # Apply spell correction before fallback extraction
            corrected_text = correct_text(request.inputs.user_text, vitals_only=request.requested_outputs.include_vitals)
            
            vitals = None
            if request.requested_outputs.include_vitals:
                vitals = self._extract_vitals_from_text(corrected_text)
            
            # Generate summary from corrected user text if requested
            summary = None
            if request.requested_outputs.include_summary:
                summary = corrected_text[:200] + "..." if len(corrected_text) > 200 else corrected_text
            
            # Return error response in V2 format
            return AutoPopulationResponseV2(
                request_id=request.request_id,
                task_type=request.task_type,
                outputs=Outputs(
                    summary=summary,
                    structured_fields=None,
                    vitals=vitals
                ),
                quality=None if not request.requested_outputs.include_quality_indicators else Quality(
                    warnings=[
                        Warning(
                            level="error",
                            message=f"Processing failed: {str(e)}",
                            field_name=None
                        )
                    ]
                ),
                trace=None if not request.requested_outputs.include_trace else Trace(),
                metadata=Metadata(
                    model_used=settings.openai_model
                )
            )
    
    def _convert_v1_to_v2_response(
        self,
        v1_response,
        v2_request: AutoPopulationRequestV2
    ) -> AutoPopulationResponseV2:
        """Convert V1 response to V2 format."""
        
        # Extract vitals if requested separately
        vitals = None
        if v2_request.requested_outputs.include_vitals:
            # Always include vitals if requested
            if (v1_response.structured_fields and 
                hasattr(v1_response.structured_fields, 'vitals') and 
                v1_response.structured_fields.vitals is not None):
                vitals = v1_response.structured_fields.vitals
            else:
                # If vitals weren't extracted, try to extract from user text as fallback
                # This ensures vitals are always included when requested
                vitals = self._extract_vitals_from_text(v2_request.inputs.user_text)
        
        # Build outputs - only include what was requested
        outputs = Outputs(
            summary=self._generate_summary(v1_response, v2_request.inputs.user_text) if v2_request.requested_outputs.include_summary else None,
            structured_fields=v1_response.structured_fields if v2_request.requested_outputs.include_structured_fields else None,
            vitals=vitals  # Include vitals if requested (even if None)
        )
        
        # If only summary and vitals are requested, ensure structured_fields is None
        if not v2_request.requested_outputs.include_structured_fields:
            outputs.structured_fields = None
        
        # Convert contradictions to V2 format (add confidence)
        contradictions_v2 = []
        for contradiction in v1_response.contradictions:
            contradictions_v2.append(ContradictionFlagV2(
                field_name=contradiction.field_name,
                user_text_value=contradiction.user_text_value,
                patient_record_value=contradiction.patient_record_value,
                recommendation=contradiction.recommendation,
                severity=contradiction.severity,
                confidence="medium"  # Default confidence
            ))
        
        # Convert source trace to V2 format
        # Filter to only include fields that were actually requested
        # If only vitals is requested, only show vitals in trace
        source_trace_v2 = []
        if v2_request.requested_outputs.include_structured_fields:
            # Include all structured fields if requested
            for trace in v1_response.source_trace:
                source_trace_v2.append(SourceTraceV2(
                    field_name=trace.field_name,
                    source=trace.source,
                    extraction_method=trace.extraction_method,
                    timestamp=trace.timestamp
                ))
        else:
            # Only vitals requested - filter to only vitals entries
            for trace in v1_response.source_trace:
                # Only include vitals-related fields
                if trace.field_name.startswith("vitals"):
                    source_trace_v2.append(SourceTraceV2(
                        field_name=trace.field_name,
                        source=trace.source,
                        extraction_method=trace.extraction_method,
                        timestamp=trace.timestamp
                    ))
        
        # Build quality (only if requested)
        quality = None
        if v2_request.requested_outputs.include_quality_indicators:
            # Re-filter uncertainty flags based on V2 expected fields (in case V1 filtering missed some)
            from app.services.field_utils import filter_uncertainty_flags_by_expected
            filtered_uncertainty_flags = filter_uncertainty_flags_by_expected(
                v1_response.uncertainty_flags,
                v2_request.get_expected_fields(),
                completeness_audit=settings.completeness_audit_mode
            )
            
            quality = Quality(
                uncertainty_flags=filtered_uncertainty_flags,
                contradictions=contradictions_v2,
                warnings=v1_response.warnings
            )
        
        # Build trace (only if requested)
        trace = None
        if v2_request.requested_outputs.include_trace:
            trace = Trace(source_trace=source_trace_v2)
        
        # Build metadata
        metadata = Metadata(
            model_used=v1_response.processing_metadata.get("model_used", settings.openai_model),
            processing_timestamp=datetime.fromisoformat(
                v1_response.processing_metadata.get("processing_timestamp", datetime.utcnow().isoformat())
            ),
            schema_version="auto_population.v1"
        )
        
        return AutoPopulationResponseV2(
            request_id=v1_response.request_id,
            task_type=v1_response.task_type,
            outputs=outputs,
            quality=quality,
            trace=trace,
            metadata=metadata
        )
    
    def _extract_vitals_from_text(self, user_text: str) -> Dict[str, Any]:
        """
        Fallback: Extract vitals from user text using simple pattern matching.
        This ensures vitals are always included when requested, even if AI extraction fails.
        Applies spell correction before extraction for better accuracy.
        """
        import re
        
        # Apply spell correction before extraction (correct_text is imported at module level)
        corrected_text = correct_text(user_text, vitals_only=True)
        # Vitals structure matching the form: BP, HR, Temp, O2 Sat, RR, plus optional fields
        vitals = {
            "bp": None,  # Blood pressure (systolic/diastolic, e.g., "150/90")
            "hr": None,  # Heart rate (bpm)
            "temp": None,  # Temperature (Celsius)
            "o2_sat": None,  # Oxygen saturation (%)
            "rr": None,  # Respiratory rate (bpm)
            "map": None,  # Mean Arterial Pressure (calculated from BP, optional)
            "measurement_site": None,  # Measurement site (e.g., "arm", "leg", optional)
            "note": None  # Additional notes about vitals (optional)
        }
        
        text_lower = corrected_text.lower()  # Use corrected text for extraction
        
        # Extract blood pressure (e.g., "150/90", "BP 150/90", "blood pressure is 150/90")
        bp_patterns = [
            r'blood\s+pressure\s+(?:is\s+)?(\d{2,3}/\d{2,3})',
            r'bp\s+(?:is\s+)?(\d{2,3}/\d{2,3})',
            r'(\d{2,3}/\d{2,3})\s*(?:mmhg|bp|blood\s+pressure)',
        ]
        for pattern in bp_patterns:
            match = re.search(pattern, text_lower)
            if match:
                vitals["bp"] = match.group(1)
                break
        
        # Extract heart rate (e.g., "95 bpm", "HR 95", "heart rate 95 bpm")
        hr_patterns = [
            r'heart\s+rate\s+(?:is\s+)?(\d{2,3})\s*(?:bpm|beats)',
            r'hr\s+(?:is\s+)?(\d{2,3})\s*(?:bpm|beats)',
            r'(\d{2,3})\s*(?:bpm|beats)\s*(?:per\s+minute|heart\s+rate|hr)'
        ]
        for pattern in hr_patterns:
            match = re.search(pattern, text_lower)
            if match:
                vitals["hr"] = match.group(1) + " bpm"
                break
        
        return vitals
    
    def _generate_summary(self, v1_response, user_text: str = None) -> str:
        """
        Generate a concise summary from the structured fields or user text.
        If structured fields are minimal (only vitals), generate from user text.
        """
        # If we have structured fields with clinical data, use them
        if (v1_response.structured_fields.chief_complaint or 
            v1_response.structured_fields.diagnosis or 
            v1_response.structured_fields.assessment or 
            v1_response.structured_fields.plan):
            
            parts = []
            
            # Chief complaint
            if v1_response.structured_fields.chief_complaint:
                parts.append(v1_response.structured_fields.chief_complaint)
            
            # History of present illness (brief)
            if v1_response.structured_fields.history_of_present_illness:
                hpi = v1_response.structured_fields.history_of_present_illness
                # Take first sentence if it's long
                if len(hpi) > 100 and "." in hpi:
                    hpi = hpi.split(".")[0] + "."
                parts.append(hpi)
            
            # Diagnosis (avoid duplication with assessment)
            if v1_response.structured_fields.diagnosis:
                diagnoses = ", ".join(v1_response.structured_fields.diagnosis)
                # Only add if assessment doesn't already contain it
                assessment_text = v1_response.structured_fields.assessment or ""
                if diagnoses.lower() not in assessment_text.lower():
                    parts.append(f"Diagnosis: {diagnoses}")
            
            # Assessment (only if different from diagnosis)
            if v1_response.structured_fields.assessment:
                assessment = v1_response.structured_fields.assessment
                # Check if it's just repeating the diagnosis
                if v1_response.structured_fields.diagnosis:
                    diagnosis_text = ", ".join(v1_response.structured_fields.diagnosis).lower()
                    if diagnosis_text not in assessment.lower():
                        parts.append(f"Assessment: {assessment}")
                else:
                    parts.append(f"Assessment: {assessment}")
            
            # Plan
            if v1_response.structured_fields.plan:
                parts.append(f"Plan: {v1_response.structured_fields.plan}")
            
            # Join with periods and clean up
            summary = ". ".join(parts)
            # Remove duplicate periods
            summary = summary.replace("..", ".").replace(". .", ".")
            
            return summary if summary else "No summary available."
        else:
            # If no structured fields, generate simple summary from user text
            if user_text:
                # Take first 200 characters or first sentence
                if len(user_text) > 200:
                    if "." in user_text[:200]:
                        summary = user_text[:user_text[:200].rfind(".") + 1]
                    else:
                        summary = user_text[:200] + "..."
                else:
                    summary = user_text
                return summary
            return "No summary available."

