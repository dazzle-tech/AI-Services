"""OpenAI client for clinical recommendations generation - optimized for GPT-4."""
import json
import logging
import time
from typing import Dict, Any, List, Optional
from openai import OpenAI
from openai import APIError, RateLimitError, APITimeoutError, APIConnectionError
from app.core.config import settings
from app.ai.prompts import (
    build_recommendations_prompt,
    build_specialty_prompt,
    build_role_based_prompt
)
from app.models.schemas import ClinicalRecommendation, RecommendationType, RecommendationPriority

logger = logging.getLogger(__name__)


class AIClient:
    """Client for interacting with OpenAI API - optimized for GPT-4."""
    
    def __init__(self):
        """Initialize OpenAI client."""
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY must be set")
        self.client = OpenAI(
            api_key=settings.openai_api_key,
            timeout=settings.openai_timeout
        )
        self.model = settings.openai_model
        self.temperature = settings.openai_temperature
        self.max_tokens = settings.openai_max_tokens
        self.max_retries = settings.openai_max_retries
        self.retry_delay = settings.openai_retry_delay
    
    def generate_recommendations(
        self,
        patient_context: Dict[str, Any],
        recommendation_types: List[str],
        focus_areas: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Generate clinical recommendations from patient context using GPT-4.
        
        Args:
            patient_context: Dictionary containing patient information
            recommendation_types: List of recommendation types to generate
            focus_areas: Optional list of specific focus areas
            
        Returns:
            Dictionary containing recommendations, summary, and priority breakdown
            
        Raises:
            ValueError: If recommendation generation fails after retries
            RateLimitError: If rate limit is exceeded
        """
        # Build prompt
        messages = build_recommendations_prompt(patient_context, recommendation_types, focus_areas)
        
        # Use internal API call method
        return self._call_openai_api(messages)
    
    def parse_recommendations(self, ai_response: Dict[str, Any]) -> List[ClinicalRecommendation]:
        """Parse AI response into ClinicalRecommendation objects."""
        recommendations = []
        
        recommendations_data = ai_response.get("recommendations", [])
        
        for idx, rec_data in enumerate(recommendations_data):
            try:
                # Generate recommendation ID if not provided
                rec_id = rec_data.get("recommendation_id", f"rec_{idx + 1}")

                rec_type = self._normalize_recommendation_type(rec_data)
                
                # Parse priority
                priority_str = rec_data.get("priority", "moderate")
                try:
                    priority = RecommendationPriority(priority_str)
                except ValueError:
                    priority = RecommendationPriority.MODERATE
                
                recommendation = ClinicalRecommendation(
                    recommendation_id=rec_id,
                    type=rec_type,
                    title=rec_data.get("title", "Untitled Recommendation"),
                    description=rec_data.get("description", ""),
                    rationale=rec_data.get("rationale", ""),
                    priority=priority,
                    actionable_steps=rec_data.get("actionable_steps", []),
                    evidence_level=rec_data.get("evidence_level"),
                    contraindications=rec_data.get("contraindications", []),
                    monitoring_requirements=rec_data.get("monitoring_requirements"),
                    follow_up=rec_data.get("follow_up")
                )
                recommendations.append(recommendation)
                
            except Exception as e:
                logger.warning(f"Error parsing recommendation {idx}: {e}")
                logger.debug(f"Recommendation data: {rec_data}")
                continue
        
        return recommendations

    def _normalize_recommendation_type(self, rec_data: Dict[str, Any]) -> RecommendationType:
        """Normalize model output into one of the supported RecommendationType enum values."""
        raw_type = str(rec_data.get("type", "") or "").strip().lower()
        title = str(rec_data.get("title", "") or "").lower()
        description = str(rec_data.get("description", "") or "").lower()
        rationale = str(rec_data.get("rationale", "") or "").lower()
        combined_text = " ".join([title, description, rationale])

        if raw_type:
            try:
                return RecommendationType(raw_type)
            except ValueError:
                pass

        alias_map = {
            "medical": RecommendationType.GENERAL,
            "medicine": RecommendationType.GENERAL,
            "drug": RecommendationType.MEDICATION,
            "meds": RecommendationType.MEDICATION,
            "test": RecommendationType.DIAGNOSTIC,
            "tests": RecommendationType.DIAGNOSTIC,
            "imaging": RecommendationType.DIAGNOSTIC,
            "scan": RecommendationType.DIAGNOSTIC,
            "therapy": RecommendationType.TREATMENT,
            "management": RecommendationType.TREATMENT,
            "followup": RecommendationType.MONITORING,
            "follow-up": RecommendationType.MONITORING,
            "observation": RecommendationType.MONITORING,
            "diet": RecommendationType.LIFESTYLE,
            "exercise": RecommendationType.LIFESTYLE,
            "prevention": RecommendationType.LIFESTYLE,
            "consult": RecommendationType.REFERRAL,
            "consultation": RecommendationType.REFERRAL,
            "specialist": RecommendationType.REFERRAL,
        }

        if raw_type in alias_map:
            normalized = alias_map[raw_type]
            logger.warning("Mapped unsupported recommendation type '%s' to '%s'", raw_type, normalized.value)
            return normalized

        keyword_map = [
            (("aspirin", "statin", "beta-blocker", "ace inhibitor", "dose", "medication"), RecommendationType.MEDICATION),
            (("ecg", "echo", "troponin", "lab", "imaging", "diagnostic", "test"), RecommendationType.DIAGNOSTIC),
            (("treat", "therapy", "intervention", "management", "procedure"), RecommendationType.TREATMENT),
            (("monitor", "trend", "surveillance", "follow-up", "recheck"), RecommendationType.MONITORING),
            (("lifestyle", "diet", "exercise", "smoking", "weight"), RecommendationType.LIFESTYLE),
            (("refer", "referral", "cardiology", "endocrinology", "rehab"), RecommendationType.REFERRAL),
        ]

        for keywords, normalized in keyword_map:
            if any(keyword in combined_text for keyword in keywords):
                if raw_type:
                    logger.warning(
                        "Inferred recommendation type '%s' from content for unsupported type '%s'",
                        normalized.value,
                        raw_type,
                    )
                return normalized

        if raw_type:
            logger.warning("Could not parse type '%s', using GENERAL", raw_type)
        return RecommendationType.GENERAL
    
    def generate_specialty_recommendations(
        self,
        specialty: str,
        patient_context: Dict[str, Any],
        complaint: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate specialty-specific recommendations (e.g., cardiology test procedures).
        
        Args:
            specialty: Medical specialty (e.g., "cardiology")
            patient_context: Dictionary containing patient information
            complaint: Optional patient complaint
            
        Returns:
            Dictionary containing specialty-specific recommendations
        """
        messages = build_specialty_prompt(specialty, patient_context, complaint)
        
        return self._call_openai_api(messages)
    
    def generate_role_based_recommendations(
        self,
        user_role: str,
        patient_context: Dict[str, Any],
        recommendation_types: List[str],
        complaint: Optional[str] = None,
        focus_areas: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Generate recommendations from a specific user role/specialty perspective.
        
        Args:
            user_role: User's medical specialty/role
            patient_context: Dictionary containing patient information
            recommendation_types: List of recommendation types
            complaint: Optional patient complaint
            focus_areas: Optional focus areas
            
        Returns:
            Dictionary containing role-based recommendations
        """
        messages = build_role_based_prompt(
            user_role, patient_context, recommendation_types, complaint, focus_areas
        )
        
        return self._call_openai_api(messages)
    
    def _call_openai_api(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        """Internal method to call OpenAI API with retry logic."""
        last_exception = None
        for attempt in range(self.max_retries):
            try:
                logger.debug(f"OpenAI API call attempt {attempt + 1}/{self.max_retries}")
                
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    timeout=settings.openai_timeout,
                    response_format={"type": "json_object"}
                )
                
                content = response.choices[0].message.content
                
                if not content:
                    raise ValueError("Empty response from GPT-4 model")
                
                try:
                    result = json.loads(content)
                except json.JSONDecodeError as e:
                    logger.error(f"JSON Parse Error: {e}")
                    logger.debug(f"Raw response: {content[:500]}")
                    raise ValueError(f"Invalid JSON response from AI model: {e}")
                
                if not isinstance(result, dict):
                    raise ValueError("AI response is not a dictionary")
                
                # Ensure required keys exist
                if "recommendations" not in result:
                    result["recommendations"] = []
                if "summary" not in result:
                    result["summary"] = "No summary provided"
                if "priority_breakdown" not in result:
                    result["priority_breakdown"] = {}
                
                if settings.enable_usage_tracking:
                    usage = response.usage
                    logger.info(
                        f"Token usage - Prompt: {usage.prompt_tokens}, "
                        f"Completion: {usage.completion_tokens}, "
                        f"Total: {usage.total_tokens}"
                    )
                
                return result
                
            except RateLimitError as e:
                last_exception = e
                wait_time = self.retry_delay * (2 ** attempt)
                logger.warning(f"Rate limit exceeded, retrying in {wait_time}s: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(wait_time)
                else:
                    raise ValueError(f"Rate limit exceeded after {self.max_retries} attempts")
                    
            except (APITimeoutError, APIConnectionError) as e:
                last_exception = e
                wait_time = self.retry_delay * (attempt + 1)
                logger.warning(f"API connection error, retrying in {wait_time}s: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(wait_time)
                else:
                    raise ValueError(f"API connection failed after {self.max_retries} attempts: {str(e)}")
                    
            except APIError as e:
                logger.error(f"OpenAI API error: {e}")
                raise ValueError(f"OpenAI API error: {str(e)}")
                
            except Exception as e:
                logger.error(f"Unexpected error in AI recommendations generation: {e}")
                raise ValueError(f"AI recommendations generation failed: {str(e)}")
        
        raise ValueError(f"Failed to generate recommendations after {self.max_retries} attempts: {str(last_exception)}")

