"""OpenAI client for structured medical data extraction."""
import json
import logging
from typing import Dict, Any, List, Optional
from openai import OpenAI
from app.core.config import settings
from app.core.constants import UserRole, SupportedLanguage
from app.ai.prompts import build_complete_prompt

logger = logging.getLogger(__name__)


class AIClient:
    """Client for interacting with OpenAI API."""
    
    def __init__(self):
        """Initialize OpenAI client."""
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY must be set")
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model
        self.temperature = settings.openai_temperature
        self.max_tokens = settings.openai_max_tokens
    
    def extract_structured_data(
        self,
        user_text: str,
        patient_data: Dict[str, Any],
        user_role: UserRole,
        department: str,
        expected_fields: List[str],
        input_language: SupportedLanguage,
        output_language: SupportedLanguage,
        vitals_only: bool = False
    ) -> Dict[str, Any]:
        """
        Extract structured medical data from free text.
        
        Returns:
            Dict containing structured_fields, uncertainty_flags, contradictions, source_trace
        """
        try:
            # Build prompt
            messages = build_complete_prompt(
                user_text=user_text,
                patient_data=patient_data,
                user_role=user_role,
                department=department,
                expected_fields=expected_fields,
                input_language=input_language,
                output_language=output_language
            )
            
            # Use reduced tokens if only vitals are requested (faster processing)
            max_tokens = settings.openai_max_tokens_vitals_only if vitals_only else self.max_tokens
            
            # Call OpenAI API with JSON response format
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"}  # Force JSON output
            )
            
            # Extract content
            content = response.choices[0].message.content
            
            if not content:
                raise ValueError("Empty response from AI model")
            
            # Parse JSON
            try:
                result = json.loads(content)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON response: {e}")
                logger.error(f"Response content: {content[:500]}")
                raise ValueError(f"Invalid JSON response from AI model: {e}")
            
            # Validate structure
            if not isinstance(result, dict):
                raise ValueError("AI response is not a dictionary")
            
            # Ensure required keys exist
            required_keys = ["structured_fields"]
            for key in required_keys:
                if key not in result:
                    result[key] = {}
            
            # Ensure optional keys exist with defaults
            if "uncertainty_flags" not in result:
                result["uncertainty_flags"] = []
            if "contradictions" not in result:
                result["contradictions"] = []
            if "source_trace" not in result:
                result["source_trace"] = []
            
            return result
            
        except Exception as e:
            logger.error(f"Error in AI extraction: {e}")
            raise ValueError(f"AI extraction failed: {str(e)}")

