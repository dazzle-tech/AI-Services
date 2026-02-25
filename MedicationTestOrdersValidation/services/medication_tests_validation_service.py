from openai import AsyncOpenAI
import json
import logging
from typing import Dict, Any, List
from datetime import datetime

from models.schemas import (
    MedicationValidationRequest,
    TestValidationRequest,
    ValidationResponse,
    QuickSummary,
    DetailedValidation,
    RecommendedAlternative
)
from config import settings, Status, Severity

logger = logging.getLogger(__name__)


class BaseValidationService:
    """Base class for validation services"""
    
    def __init__(self):
        """Initialize OpenAI client"""
        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is not set in environment variables")
        
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = settings.OPENAI_MODEL
        self.temperature = settings.OPENAI_TEMPERATURE
        self.max_tokens = settings.OPENAI_MAX_TOKENS
    
    async def call_openai(self, system_prompt: str, user_message: str) -> Dict[str, Any]:
        """
        Call OpenAI API with retry logic
        
        Args:
            system_prompt: System prompt for the model
            user_message: User message containing data to validate
            
        Returns:
            Parsed JSON response from the model
        """
        for attempt in range(settings.MAX_RETRY_ATTEMPTS):
            try:
                logger.info(f"Calling OpenAI API (attempt {attempt + 1})")
                
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message}
                    ],
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    response_format={"type": "json_object"}
                )
                
                content = response.choices[0].message.content
                result = json.loads(content)
                
                logger.info("OpenAI API call successful")
                return result
                
            except json.JSONDecodeError as e:
                logger.error(f"JSON decode error: {str(e)}")
                if attempt == settings.MAX_RETRY_ATTEMPTS - 1:
                    raise Exception("Failed to parse OpenAI response as JSON")
                    
            except Exception as e:
                logger.error(f"OpenAI API error: {str(e)}")
                if attempt == settings.MAX_RETRY_ATTEMPTS - 1:
                    raise Exception(f"OpenAI API call failed: {str(e)}")
        
        raise Exception("Max retry attempts reached")
    
    def parse_validation_response(self, api_response: Dict[str, Any]) -> ValidationResponse:
        """
        Parse OpenAI response into ValidationResponse model
        
        Args:
            api_response: Raw response from OpenAI
            
        Returns:
            Validated ValidationResponse object
        """
        try:
            # Parse quick summary
            quick_summary = QuickSummary(
                overall_status=api_response["quick_summary"]["overall_status"],
                top_priority=api_response["quick_summary"]["top_priority"]
            )
            
            # Parse detailed validations
            detailed_validations = [
                DetailedValidation(**validation)
                for validation in api_response.get("detailed_validations", [])
            ]
            
            # Parse recommended alternatives
            recommended_alternatives = [
                RecommendedAlternative(**alt)
                for alt in api_response.get("recommended_alternatives", [])
            ]
            
            # Get confidence score
            confidence_score = float(api_response.get("confidence_score", 0.85))
            
            return ValidationResponse(
                quick_summary=quick_summary,
                detailed_validations=detailed_validations,
                recommended_alternatives=recommended_alternatives,
                confidence_score=confidence_score
            )
            
        except Exception as e:
            logger.error(f"Error parsing validation response: {str(e)}")
            raise Exception(f"Failed to parse validation response: {str(e)}")


class MedicationValidationService(BaseValidationService):
    """Service for validating medications"""
    
    async def validate(self, request: MedicationValidationRequest) -> ValidationResponse:
        """
        Validate medications against patient data
        
        Args:
            request: Medication validation request
            
        Returns:
            ValidationResponse with safety assessment
        """
        logger.info(f"Starting medication validation for patient {request.patient.mrn}")
        
        # Prepare user message with patient and medication data
        user_message = self._prepare_medication_message(request)
        
        # Call OpenAI
        api_response = await self.call_openai(
            system_prompt=settings.MEDICATION_VALIDATION_SYSTEM_PROMPT,
            user_message=user_message
        )
        
        # Parse and return response
        result = self.parse_validation_response(api_response)
        
        logger.info(f"Medication validation completed: {result.quick_summary.overall_status}")
        return result
    
    def _prepare_medication_message(self, request: MedicationValidationRequest) -> str:
        """Prepare the user message for medication validation"""
        
        message = f"""Please validate the following medication prescription for safety concerns.

PATIENT INFORMATION:
- MRN: {request.patient.mrn}
- Name: {request.patient.fullName}
- Gender: {request.patient.gender}
- Date of Birth: {request.patient.dob}
- Age: {request.encounter.patientAge}

ENCOUNTER INFORMATION:
- Visit ID: {request.encounter.visitId}
- Visit Type: {request.encounter.visitType}
- Date: {request.encounter.plannedStartDate}
- Chief Complaint: {request.encounter.chiefComplaint}
- Diagnosis: {request.encounter.diagnosis}

MEDICATIONS TO VALIDATE:
{self._format_medications(request.medications)}

Please analyze for:
1. Drug-drug interactions between the medications
2. Age-appropriate dosing
3. Gender-specific considerations
4. Contraindications based on the diagnosis
5. Dosage safety and appropriateness
6. Duration concerns
7. Any duplicate therapy

Respond with a JSON object containing:
{{
  "quick_summary": {{
    "overall_status": "SAFE|CAUTION|CONTRAINDICATED",
    "top_priority": "Most critical issue or 'No critical issues found'"
  }},
  "detailed_validations": [
    {{
      "item": "medication name",
      "severity": "critical|high|moderate|low|info",
      "issue": "description of the issue",
      "recommendation": "recommended action",
      "evidence": "clinical reasoning"
    }}
  ],
  "recommended_alternatives": [
    {{
      "original_item": "medication name",
      "alternative": "suggested alternative",
      "rationale": "reason for recommendation"
    }}
  ],
  "confidence_score": 0.95
}}
"""
        return message
    
    def _format_medications(self, medications: List[str]) -> str:
        """Format medications list for display"""
        formatted = []
        for i, med in enumerate(medications, 1):
            formatted.append(f"{i}. {med}")
        return "\n".join(formatted)


class TestValidationService(BaseValidationService):
    """Service for validating diagnostic tests"""
    
    async def validate(self, request: TestValidationRequest) -> ValidationResponse:
        """
        Validate diagnostic tests against patient data
        
        Args:
            request: Test validation request
            
        Returns:
            ValidationResponse with safety assessment
        """
        logger.info(f"Starting test validation for patient {request.patient.mrn}")
        
        # Prepare user message with patient and test data
        user_message = self._prepare_test_message(request)
        
        # Call OpenAI
        api_response = await self.call_openai(
            system_prompt=settings.TEST_VALIDATION_SYSTEM_PROMPT,
            user_message=user_message
        )
        
        # Parse and return response
        result = self.parse_validation_response(api_response)
        
        logger.info(f"Test validation completed: {result.quick_summary.overall_status}")
        return result
    
    def _prepare_test_message(self, request: TestValidationRequest) -> str:
        """Prepare the user message for test validation"""
        
        message = f"""Please validate the following diagnostic test order for appropriateness and safety.

PATIENT INFORMATION:
- MRN: {request.patient.mrn}
- Name: {request.patient.fullName}
- Gender: {request.patient.gender}
- Date of Birth: {request.patient.dob}
- Age: {request.encounter.patientAge}

ENCOUNTER INFORMATION:
- Visit ID: {request.encounter.visitId}
- Visit Type: {request.encounter.visitType}
- Date: {request.encounter.plannedStartDate}
- Chief Complaint: {request.encounter.chiefComplaint}
- Diagnosis: {request.encounter.diagnosis}

DIAGNOSTIC TESTS TO VALIDATE:
{self._format_tests(request.tests)}

Please analyze for:
1. Test appropriateness for age and gender
2. Relevance to chief complaint and diagnosis
3. Any contraindications based on patient condition
4. Redundant or duplicate tests
5. Test sequencing or priority issues
6. Missing critical tests that should be ordered
7. Priority and urgency appropriateness

Respond with a JSON object containing:
{{
  "quick_summary": {{
    "overall_status": "SAFE|CAUTION|CONTRAINDICATED",
    "top_priority": "Most critical issue or 'No critical issues found'"
  }},
  "detailed_validations": [
    {{
      "item": "test name",
      "severity": "critical|high|moderate|low|info",
      "issue": "description of the issue",
      "recommendation": "recommended action",
      "evidence": "clinical reasoning"
    }}
  ],
  "recommended_alternatives": [
    {{
      "original_item": "test name",
      "alternative": "suggested alternative or additional test",
      "rationale": "reason for recommendation"
    }}
  ],
  "confidence_score": 0.95
}}
"""
        return message
    
    def _format_tests(self, tests: List[str]) -> str:
        """Format tests list for display"""
        formatted = []
        for i, test in enumerate(tests, 1):
            formatted.append(f"{i}. {test}")
        return "\n".join(formatted)