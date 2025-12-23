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
    apply_role_restrictions,
    check_contradictions,
    validate_json_structure,
    deduplicate_contradictions
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
            logger.info(f"Processing request {request.request_id} for user {request.user_context.user_id}")
            
            # Check if only vitals are requested (for optimization)
            # Use passed flag or determine from expected_output
            if not vitals_only:
                vitals_only = len(request.expected_output) == 1 and "vitals" in request.expected_output
            
            ai_result = self.ai_client.extract_structured_data(
                user_text=request.user_text,
                patient_data=request.patient_data,
                user_role=request.user_context.user_role,
                department=request.user_context.department,
                expected_fields=request.expected_output,
                input_language=request.input_language,
                output_language=request.output_language,
                vitals_only=vitals_only
            )
            
            # Step 2: Validate JSON structure
            validate_json_structure(ai_result)
            
            # Step 3: Apply role-based restrictions
            structured_fields_dict = ai_result.get("structured_fields", {})
            filtered_fields = apply_role_restrictions(
                structured_fields_dict,
                request.user_context.user_role
            )
            
            # Step 4: Validate extracted fields
            warnings = validate_extracted_fields(
                filtered_fields,
                request.expected_output,
                request.user_context.user_role
            )
            
            # Step 5: Check for contradictions (backend deterministic checks)
            backend_contradictions = check_contradictions(
                filtered_fields,
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
            
            # Filter uncertainty flags based on expected_output (unless completeness audit mode)
            uncertainty_flags = filter_uncertainty_flags_by_expected(
                uncertainty_flags_raw,
                request.expected_output,
                completeness_audit=settings.completeness_audit_mode
            )
            
            # Step 7: Process source trace
            source_trace = []
            ai_trace = ai_result.get("source_trace", [])
            for trace in ai_trace:
                if isinstance(trace, dict):
                    try:
                        # Ensure timestamp is set
                        if "timestamp" not in trace:
                            trace["timestamp"] = datetime.utcnow().isoformat()
                        source_trace.append(SourceTrace(**trace))
                    except Exception as e:
                        logger.warning(f"Failed to parse source trace: {e}")
            
            # Step 8: Build structured fields object
            try:
                structured_fields = StructuredFields(**filtered_fields)
            except Exception as e:
                logger.error(f"Failed to create StructuredFields: {e}")
                # Create with minimal fields if validation fails
                structured_fields = StructuredFields()
                warnings.append(Warning(
                    level="error",
                    message=f"Failed to validate structured fields: {e}",
                    field_name=None
                ))
            
            # Step 9: Build response
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
                    "processing_timestamp": datetime.utcnow().isoformat(),
                    "user_role": request.user_context.user_role.value,
                    "department": request.user_context.department
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

