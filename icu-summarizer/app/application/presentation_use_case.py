"""Use case for generating handoff presentations"""
from io import BytesIO
from typing import Dict, Any
from app.domain.input_models import ICURequestPayload
from app.domain.clinical_models import ClinicalSummary
from app.domain.normalization import ConceptNormalizer
from app.domain.trends import build_clinical_summary
from app.infrastructure.openai_client import OpenAIClient
from app.infrastructure.llm_prompt import build_structured_note_prompt, NOTE_JSON_SCHEMA
from app.infrastructure.pptx_generator import PPTXGenerator
from app.utils.errors import ExternalServiceError, ValidationError
from app.utils.time_utils import validate_timestamps_in_window


class PresentationUseCase:
    """Use case for generating handoff presentations"""
    
    def __init__(self, normalizer: ConceptNormalizer, openai_client: OpenAIClient,
                 pptx_generator: PPTXGenerator):
        """
        Initialize use case.
        
        Args:
            normalizer: Concept normalizer for flowsheet mapping
            openai_client: OpenAI client for LLM generation
            pptx_generator: PPTX generator
        """
        self.normalizer = normalizer
        self.openai_client = openai_client
        self.pptx_generator = pptx_generator
    
    def execute(self, payload: ICURequestPayload) -> BytesIO:
        """
        Execute the presentation use case.
        
        Args:
            payload: ICU request payload
            
        Returns:
            BytesIO containing PPTX file
            
        Raises:
            ValidationError: If validation fails
            ExternalServiceError: If OpenAI or PPTX generation fails
        """
        # Validate time window
        if payload.time_window.end <= payload.time_window.start:
            raise ValidationError("Time window end must be after start")
        
        # Validate and filter timestamps
        valid_flowsheet, _ = validate_timestamps_in_window(
            payload.flowsheet, payload.time_window.start, payload.time_window.end
        )
        valid_meds, _ = validate_timestamps_in_window(
            payload.meds, payload.time_window.start, payload.time_window.end
        )
        valid_labs, _ = validate_timestamps_in_window(
            payload.labs, payload.time_window.start, payload.time_window.end
        )
        valid_events, _ = validate_timestamps_in_window(
            payload.events, payload.time_window.start, payload.time_window.end
        )
        
        # Create validated payload
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
        
        # Build clinical summary
        clinical_summary = build_clinical_summary(validated_payload, self.normalizer)
        
        # Generate structured JSON note (needed for PPTX)
        try:
            json_prompt = build_structured_note_prompt(clinical_summary)
            note_json = self.openai_client.generate_structured_completion(
                json_prompt, NOTE_JSON_SCHEMA
            )
        except ExternalServiceError as e:
            raise ExternalServiceError(
                f"Failed to generate structured note for presentation: {str(e)}",
                service="OPENAI"
            )
        
        # Generate PPTX
        try:
            presentation = self.pptx_generator.generate_handoff_deck(
                note_json=note_json,
                clinical_summary=clinical_summary.model_dump(mode='json', exclude_none=True),
                patient_id=payload.patient.id
            )
            
            # Save to BytesIO
            output = BytesIO()
            presentation.save(output)
            output.seek(0)
            return output
            
        except Exception as e:
            raise ExternalServiceError(
                f"Failed to generate PPTX: {str(e)}",
                service="PPTX_GENERATOR"
            )
