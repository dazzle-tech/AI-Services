"""OpenAI client for LLM interactions"""
import json
import os
from typing import Dict, Any, Optional
from openai import OpenAI
from app.utils.errors import ExternalServiceError


class OpenAIClient:
    """Client for OpenAI API interactions"""
    
    def __init__(self, api_key: Optional[str] = None, model_name: str = "gpt-4o"):
        """
        Initialize OpenAI client.
        
        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
            model_name: Model to use (defaults to gpt-4o)
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ExternalServiceError(
                "OPENAI_API_KEY not provided and not found in environment",
                service="OPENAI"
            )
        
        self.model_name = model_name or os.getenv("MODEL_NAME", "gpt-4o")
        self.client = OpenAI(api_key=self.api_key)
    
    def generate_structured_completion(self, prompt: str, json_schema: Dict[str, Any],
                                      max_retries: int = 3) -> Dict[str, Any]:
        """
        Generate structured JSON output using OpenAI with JSON schema.
        
        Args:
            prompt: The prompt to send
            json_schema: JSON schema for structured output
            max_retries: Maximum retry attempts if parsing fails
            
        Returns:
            Parsed JSON dictionary
            
        Raises:
            ExternalServiceError: If API call fails or JSON parsing fails
        """
        for attempt in range(max_retries):
            try:
                # Use structured outputs with JSON mode
                # Note: For models that support structured outputs, use response_format
                # For others, request JSON mode and parse manually
                try:
                    # Try structured outputs API (for supported models)
                    # Note: json_schema requires a "name" field
                    response = self.client.beta.chat.completions.parse(
                        model=self.model_name,
                        messages=[
                            {"role": "system", "content": "You are a medical AI assistant. Always output valid JSON. Never invent data - if information is missing, use null or 'Not available'."},
                            {"role": "user", "content": prompt}
                        ],
                        response_format={
                            "type": "json_schema",
                            "json_schema": {
                                "name": "icu_note",
                                "schema": json_schema,
                                "strict": True
                            }
                        }
                    )
                    result = response.choices[0].message.parsed
                    if result:
                        return result
                    # Fall through to content parsing if parsed is None
                    content = response.choices[0].message.content
                except (AttributeError, TypeError):
                    # Fallback to JSON mode for models that don't support structured outputs
                    response = self.client.chat.completions.create(
                        model=self.model_name,
                        messages=[
                            {"role": "system", "content": "You are a medical AI assistant. Always output valid JSON matching the provided schema. Never invent data - if information is missing, use null or 'Not available'."},
                            {"role": "user", "content": prompt + "\n\nIMPORTANT: Respond with ONLY valid JSON matching this schema: " + json.dumps(json_schema)}
                        ],
                        response_format={"type": "json_object"},
                        temperature=0.3
                    )
                    content = response.choices[0].message.content
                
                if not content:
                    raise ExternalServiceError("Empty response from OpenAI", service="OPENAI")
                
                # Parse JSON
                result = json.loads(content)
                return result
                
            except json.JSONDecodeError as e:
                if attempt < max_retries - 1:
                    continue
                raise ExternalServiceError(
                    f"Failed to parse JSON response after {max_retries} attempts: {str(e)}",
                    service="OPENAI"
                )
            except Exception as e:
                error_msg = str(e)
                if "rate limit" in error_msg.lower():
                    raise ExternalServiceError(
                        f"OpenAI rate limit exceeded: {error_msg}",
                        service="OPENAI"
                    )
                elif "authentication" in error_msg.lower() or "api key" in error_msg.lower():
                    raise ExternalServiceError(
                        f"OpenAI authentication failed: {error_msg}",
                        service="OPENAI"
                    )
                else:
                    raise ExternalServiceError(
                        f"OpenAI API error: {error_msg}",
                        service="OPENAI"
                    )
        
        raise ExternalServiceError("Failed to get valid response from OpenAI", service="OPENAI")
    
    def generate_text_completion(self, prompt: str, temperature: float = 0.3) -> str:
        """
        Generate text completion (for markdown notes).
        
        Args:
            prompt: The prompt to send
            temperature: Sampling temperature
            
        Returns:
            Generated text
            
        Raises:
            ExternalServiceError: If API call fails
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "You are a medical AI assistant. Generate clear, concise clinical notes in markdown format. Never invent data - if information is missing, state 'Not available'."},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature
            )
            
            content = response.choices[0].message.content
            if not content:
                raise ExternalServiceError("Empty response from OpenAI", service="OPENAI")
            
            return content
            
        except Exception as e:
            error_msg = str(e)
            if "rate limit" in error_msg.lower():
                raise ExternalServiceError(
                    f"OpenAI rate limit exceeded: {error_msg}",
                    service="OPENAI"
                )
            elif "authentication" in error_msg.lower() or "api key" in error_msg.lower():
                raise ExternalServiceError(
                    f"OpenAI authentication failed: {error_msg}",
                    service="OPENAI"
                )
            else:
                raise ExternalServiceError(
                    f"OpenAI API error: {error_msg}",
                    service="OPENAI"
                )
