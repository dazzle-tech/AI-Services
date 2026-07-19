"""Service layer for auto-population task."""
import logging
from typing import Dict, Any
from datetime import datetime

from app.models.schemas import (
    AutoPopulationRequest,
    AutoPopulationResponse,
    StructuredFields,
    UncertaintyFlag,
    ContradictionFlag,
    SourceTrace,
    Warning
)
from app.ai.client import AIClient
from app.core.config import settings
from app.services.validation import (
    validate_extracted_fields,
    check_contradictions,
    validate_json_structure,
    deduplicate_contradictions,
    build_structured_fields,
    normalize_history_of_present_illness,
    filter_completed_procedures,
    build_field_source_trace
)
from app.services.field_utils import filter_uncertainty_flags_by_expected

logger = logging.getLogger(__name__)


class AutoPopulationService:
    """Service for handling auto-population requests."""
    
    def __init__(self):
        """Initialize service with AI client."""
        self.ai_client = AIClient()
    
    def process_request(self, request: AutoPopulationRequest, vitals_only: bool = False) -> AutoPopulationResponse:
        """
        Process an auto-population request.
        
        Args:
            request: Auto-population request with user text and patient data
            
        Returns:
            Auto-population response with structured data
        """
        try:
            # Step 1: Call AI client to extract structured data
            logger.info(f"Processing request {request.request_id}")
            
            # Check if only vitals are requested (for optimization)
            # Use passed flag or determine from expected_output
            if not vitals_only:
                vitals_only = len(request.expected_output) == 1 and "vitals" in request.expected_output
            
            ai_result = self.ai_client.extract_structured_data(
                user_text=request.user_text,
                patient_data=request.patient_data,
                expected_fields=request.expected_output,
                input_language=request.input_language,
                output_language=request.output_language,
                vitals_only=vitals_only
            )
            
            # Step 2: Validate JSON structure
            validate_json_structure(ai_result)
            
            # Step 3: Coerce and validate fields individually so one bad field
            # does not discard the rest of the structured payload.
            structured_fields_dict = ai_result.get("structured_fields", {})
            structured_fields, field_warnings = build_structured_fields(structured_fields_dict)

            # Keep demographic context in HPI and filter planned procedures.
            structured_fields.history_of_present_illness = normalize_history_of_present_illness(
                request.user_text,
                structured_fields.history_of_present_illness
            )
            structured_fields.procedures = filter_completed_procedures(
                structured_fields.procedures,
                request.user_text
            )
            if structured_fields.procedures == []:
                structured_fields.procedures = None
            if structured_fields.allergies is None:
                user_text_lower = request.user_text.lower()
                if any(marker in user_text_lower for marker in ("no known allergies", "nkda", "no allergies")):
                    structured_fields.allergies = []

            structured_fields_dict = structured_fields.model_dump(exclude_none=True)

            # Step 4: Validate extracted fields
            warnings = field_warnings + validate_extracted_fields(
                structured_fields_dict,
                request.expected_output
            )

            # Step 5: Check for contradictions (backend deterministic checks)
            backend_contradictions = check_contradictions(
                structured_fields_dict,
                request.patient_data
            )
            
            # Option A: Backend-only contradictions (recommended - clean, deterministic)
            # Option B: Merge with AI contradictions (more flexible but can be noisier)
            if settings.use_backend_only_contradictions:
                # Use only backend deterministic checks (cleaner, no duplicates)
                contradictions = backend_contradictions
            else:
                # Merge AI-detected contradictions (with default severity if not provided)
                ai_contradictions = ai_result.get("contradictions", [])
                for ai_contradiction in ai_contradictions:
                    if isinstance(ai_contradiction, dict):
                        try:
                            # Ensure severity is set (default to medium if not provided)
                            if "severity" not in ai_contradiction:
                                ai_contradiction["severity"] = "medium"
                            backend_contradictions.append(ContradictionFlag(**ai_contradiction))
                        except Exception as e:
                            logger.warning(f"Failed to parse AI contradiction: {e}")
                
                # Deduplicate contradictions (prefer backend checks, merge intelligently)
                contradictions = deduplicate_contradictions(backend_contradictions)
            
            # Step 6: Process uncertainty flags
            uncertainty_flags_raw = []
            ai_uncertainty = ai_result.get("uncertainty_flags", [])
            for flag in ai_uncertainty:
                if isinstance(flag, dict):
                    try:
                        uncertainty_flags_raw.append(UncertaintyFlag(**flag))
                    except Exception as e:
                        logger.warning(f"Failed to parse uncertainty flag: {e}")

            # Every contradiction should have a matching uncertainty flag.
            existing_uncertainty_fields = {flag.field_name for flag in uncertainty_flags_raw}
            for contradiction in contradictions:
                if contradiction.field_name not in existing_uncertainty_fields:
                    uncertainty_flags_raw.append(UncertaintyFlag(
                        field_name=contradiction.field_name,
                        reason=self._build_uncertainty_reason_from_contradiction(contradiction),
                        confidence="high"
                    ))
                    existing_uncertainty_fields.add(contradiction.field_name)
            
            # Filter uncertainty flags based on expected_output (unless completeness audit mode)
            uncertainty_flags = filter_uncertainty_flags_by_expected(
                uncertainty_flags_raw,
                request.expected_output,
                completeness_audit=settings.completeness_audit_mode
            )
            
            # Step 7: Process source trace
            source_trace_map = {}
            ai_trace = ai_result.get("source_trace", [])
            for trace in ai_trace:
                if isinstance(trace, dict):
                    try:
                        if "timestamp" not in trace:
                            trace["timestamp"] = datetime.utcnow().isoformat()
                        parsed_trace = SourceTrace(**trace)
                        source_trace_map.setdefault(parsed_trace.field_name, []).append(parsed_trace)
                    except Exception as e:
                        logger.warning(f"Failed to parse source trace: {e}")

            field_sources = {
                "chief_complaint": "user_text",
                "history_of_present_illness": "user_text",
                "diagnosis": "user_text",
                "medications": "user_text",
                "vitals": "user_text",
                "procedures": "user_text",
                "allergies": "user_text",
                "assessment": "user_text",
                "plan": "user_text",
                "past_medical_history": "patient_record" if request.patient_data.get("past_medical_history") else "user_text",
                "family_history": "user_text",
                "social_history": "user_text",
                "review_of_systems": "user_text",
            }
            for field_name, default_source in field_sources.items():
                if field_name not in structured_fields_dict:
                    continue
                trace_payload = build_field_source_trace(
                    field_name=field_name,
                    user_text=request.user_text,
                    patient_data=request.patient_data,
                    structured_fields=structured_fields_dict,
                    default_source=default_source
                )
                trace_payload["timestamp"] = datetime.utcnow().isoformat()
                new_trace = SourceTrace(**trace_payload)
                traces = source_trace_map.setdefault(field_name, [])
                if new_trace.source == "user_text":
                    traces = [trace for trace in traces if trace.source == "user_text"]
                    source_trace_map[field_name] = traces
                if not any(existing.source == new_trace.source for existing in traces):
                    traces.append(new_trace)

            source_trace = []
            for traces in source_trace_map.values():
                source_trace.extend(traces)
            
            # Step 8: Build response
            response = AutoPopulationResponse(
                request_id=request.request_id,
                task_type="auto_population",
                output_language=request.output_language,
                structured_fields=structured_fields,
                uncertainty_flags=uncertainty_flags,
                contradictions=contradictions,
                source_trace=source_trace,
                warnings=warnings,
                processing_metadata={
                    "model_used": self.ai_client.model,
                    "processing_timestamp": datetime.utcnow().isoformat()
                }
            )
            
            logger.info(f"Successfully processed request {request.request_id}")
            return response
            
        except Exception as e:
            logger.error(f"Error processing request {request.request_id}: {e}")
            # Return error response with minimal valid structure
            return AutoPopulationResponse(
                request_id=request.request_id,
                task_type="auto_population",
                output_language=request.output_language,
                structured_fields=StructuredFields(),
                warnings=[
                    Warning(
                        level="error",
                        message=f"Processing failed: {str(e)}",
                        field_name=None
                    )
                ],
                processing_metadata={
                    "error": str(e),
                    "processing_timestamp": datetime.utcnow().isoformat()
                }
            )

    def _build_uncertainty_reason_from_contradiction(self, contradiction: ContradictionFlag) -> str:
        """Translate a contradiction into a clinician-facing uncertainty reason."""
        field_name = contradiction.field_name
        if field_name.startswith("vitals."):
            vital_name = field_name.split(".", 1)[1].upper()
            return f"Clinical text states {vital_name} differently than the patient record and requires clinician verification."
        if field_name == "medications":
            return "Medication details differ between the clinical text and patient record and require clinician verification."
        if field_name == "allergies":
            return "Allergy information differs between the clinical text and patient record and require clinician verification."
        return f"Clinical text conflicts with the patient record for '{field_name}' and requires clinician verification."
