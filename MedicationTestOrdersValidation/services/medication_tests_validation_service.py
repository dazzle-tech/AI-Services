from openai import AsyncOpenAI
import json
import logging
import re
from typing import Dict, Any, List
from datetime import datetime

from models.schemas import (
    MedicationValidationRequest,
    TestValidationRequest,
    AllergyDrugValidationRequest,
    Diagnosis,
    ValidationResponse,
    QuickSummary,
    DetailedValidation,
    RecommendedAlternative
)
from config import settings, Status, Severity
from services.allergy_drug_rules import merge_validation_response, run_deterministic_checks

logger = logging.getLogger(__name__)
_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)
_OPEN_THINK_RE = re.compile(r"<think>", re.IGNORECASE)
_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)


def _strip_model_wrappers(raw_text: str) -> str:
    clean = _THINK_BLOCK_RE.sub("", (raw_text or "").strip())
    if _OPEN_THINK_RE.search(clean):
        brace = clean.find("{")
        clean = clean[brace:] if brace != -1 else _OPEN_THINK_RE.sub("", clean)
    fence = _JSON_FENCE_RE.search(clean)
    if fence:
        return fence.group(1).strip()
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[-1]
        clean = clean.rsplit("```", 1)[0]
    return clean.strip()


def _extract_first_json_object(raw_text: str) -> str | None:
    start = -1
    depth = 0
    in_string = False
    escape = False

    for index, char in enumerate(raw_text):
        if start < 0:
            if char == "{":
                start = index
                depth = 1
            continue

        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return raw_text[start : index + 1]
    return None


def _parse_json_object(raw_text: str) -> Dict[str, Any]:
    cleaned = _strip_model_wrappers(raw_text)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        candidate = _extract_first_json_object(cleaned)
        if not candidate:
            raise
        parsed = json.loads(candidate)

    if not isinstance(parsed, dict):
        raise json.JSONDecodeError(
            "Model response was JSON but not an object",
            cleaned,
            0,
        )
    return parsed


class BaseValidationService:
    """Base class for validation services"""
    
    def __init__(self):
        """Initialize OpenAI client"""
        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is not set in environment variables")

        # Empty/whitespace base_url must be omitted so the SDK uses the cloud default.
        base_url = (settings.OPENAI_BASE_URL or "").strip() or None
        client_kwargs = {
            "api_key": settings.OPENAI_API_KEY,
            "timeout": settings.OPENAI_TIMEOUT,
            "max_retries": settings.OPENAI_MAX_RETRIES,
        }
        if base_url:
            client_kwargs["base_url"] = base_url

        self.client = AsyncOpenAI(**client_kwargs)
        self.base_url = base_url or "https://api.openai.com/v1"
        self.model = settings.OPENAI_MODEL
        self.temperature = settings.OPENAI_TEMPERATURE
        self.max_tokens = settings.OPENAI_MAX_TOKENS
        self.timeout = settings.OPENAI_TIMEOUT

    def _uses_qwen_model(self) -> bool:
        return "qwen" in (self.model or "").lower()

    def _should_disable_thinking(self) -> bool:
        return self._uses_qwen_model() or "11434" in (self.base_url or "")

    async def _create_completion(self, create_kwargs: Dict[str, Any]):
        try:
            return await self.client.chat.completions.create(**create_kwargs)
        except Exception as first_error:
            retry_kwargs = dict(create_kwargs)
            dropped = False
            if retry_kwargs.pop("extra_body", None) is not None:
                dropped = True
            error_text = str(first_error).lower()
            if "response_format" in error_text or "json_object" in error_text:
                retry_kwargs.pop("response_format", None)
                dropped = True
            if not dropped:
                raise
            logger.warning("Retrying model call without unsupported JSON/thinking options: %s", first_error)
            return await self.client.chat.completions.create(**retry_kwargs)

    async def call_openai(self, system_prompt: str, user_message: str) -> Dict[str, Any]:
        """
        Call OpenAI API with retry logic
        
        Args:
            system_prompt: System prompt for the model
            user_message: User message containing data to validate
            
        Returns:
            Parsed JSON response from the model
        """
        json_only_system = (
            system_prompt
            + "\n\nReply with a single JSON object only. "
            "Do not use markdown fences or <think> tags."
        )
        json_only_user = user_message
        if self._uses_qwen_model():
            json_only_user = f"{user_message.rstrip()}\n\n/no_think"

        for attempt in range(settings.MAX_RETRY_ATTEMPTS):
            content = ""
            try:
                logger.info(f"Calling OpenAI API (attempt {attempt + 1})")
                prompt_length = len(json_only_system) + len(json_only_user)
                logger.info(
                    "Calling medication/test validation using model %s base_url=%s timeout=%ss prompt_length=%s",
                    self.model,
                    self.base_url,
                    self.timeout,
                    prompt_length,
                )

                create_kwargs = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": json_only_system},
                        {"role": "user", "content": json_only_user},
                    ],
                    "temperature": self.temperature,
                    "max_tokens": self.max_tokens,
                    "response_format": {"type": "json_object"},
                    "timeout": self.timeout,
                }
                if self._should_disable_thinking():
                    create_kwargs["extra_body"] = {
                        "chat_template_kwargs": {"enable_thinking": False},
                    }

                response = await self._create_completion(create_kwargs)

                choice = response.choices[0]
                content = choice.message.content or ""
                finish_reason = getattr(choice, "finish_reason", None)
                if finish_reason == "length":
                    logger.warning(
                        "Model response truncated by max_tokens=%s; thinking may have consumed the budget",
                        self.max_tokens,
                    )
                if not content.strip():
                    reasoning = getattr(choice.message, "reasoning_content", None) or getattr(
                        choice.message, "reasoning", None
                    )
                    if reasoning:
                        logger.warning(
                            "Model returned only reasoning content (%s chars) and no JSON payload",
                            len(reasoning),
                        )
                    raise json.JSONDecodeError("Empty model response", content, 0)

                result = _parse_json_object(content)
                logger.info("OpenAI API call successful")
                return result

            except json.JSONDecodeError as e:
                logger.error(
                    "JSON decode error: %s; preview=%r",
                    str(e),
                    (content if "content" in locals() else "")[:500],
                )
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
            summary = api_response.get("quick_summary") or {}
            overall_status = str(summary.get("overall_status", "")).strip().upper()
            quick_summary = QuickSummary(
                overall_status=overall_status,
                top_priority=summary.get("top_priority") or "No issues found",
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

    def _format_diagnoses(self, diagnoses: List[Diagnosis]) -> str:
        """Format diagnoses list for display."""
        formatted = []
        for i, diagnosis in enumerate(diagnoses, 1):
            formatted.append(f"{i}. {diagnosis.type}: {diagnosis.value}")
        return "\n".join(formatted) if formatted else "None provided"


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
- Primary Diagnosis: {request.encounter.primaryDiagnosis}

LIST OF DIAGNOSES:
{self._format_diagnoses(request.listOfDiagnosis)}

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

Medication name may be blank in the input. When that happens, use the active
ingredients as the medication identifier for your analysis.

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
- Primary Diagnosis: {request.encounter.primaryDiagnosis}

LIST OF DIAGNOSES:
{self._format_diagnoses(request.listOfDiagnosis)}

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


class AllergyDrugValidationService(BaseValidationService):
    """Service for checking proposed drugs against allergies and each other."""

    async def validate(self, request: AllergyDrugValidationRequest) -> ValidationResponse:
        patient_label = "unknown"
        if request.patient and request.patient.fullName:
            patient_label = request.patient.fullName
        logger.info("Starting allergy-drug validation for patient %s", patient_label)

        user_message = self._prepare_allergy_drug_message(request)
        api_response = await self.call_openai(
            system_prompt=settings.ALLERGY_DRUG_VALIDATION_SYSTEM_PROMPT,
            user_message=user_message,
        )
        result = self.parse_validation_response(api_response)
        deterministic_findings = run_deterministic_checks(request)
        result = merge_validation_response(result, deterministic_findings)
        logger.info("Allergy-drug validation completed: %s", result.quick_summary.overall_status)
        return result

    def _prepare_allergy_drug_message(self, request: AllergyDrugValidationRequest) -> str:
        patient_block = self._format_optional_patient(request.patient)
        allergies_block = self._format_allergies(request.allergies)
        drugs_block = self._format_drugs(request.drugs)

        return f"""Please check the following drugs against the patient's documented allergies and for drug-drug interactions.

PATIENT INFORMATION (optional; omit from reasoning if not provided):
{patient_block}

DOCUMENTED ALLERGIES:
{allergies_block}

DRUGS TO VALIDATE:
{drugs_block}

Please analyze for:
1. Direct match between a listed allergy and a listed drug
2. Cross-reactivity (same drug class)
3. Drug-drug interactions between every pair of listed drugs
4. Duplicate therapy or overlapping agents in the drug list
5. Whether missing patient details change the conclusion (they should not invent data)
6. Safer alternatives when a conflict is found

Respond with a JSON object containing:
{{
  "quick_summary": {{
    "overall_status": "SAFE|CAUTION|CONTRAINDICATED",
    "top_priority": "Most critical issue or 'No allergy or drug interaction conflicts found'"
  }},
  "detailed_validations": [
    {{
      "item": "drug name",
      "severity": "critical|high|moderate|low|info",
      "issue": "description of the issue",
      "recommendation": "recommended action",
      "evidence": "clinical reasoning"
    }}
  ],
  "recommended_alternatives": [
    {{
      "original_item": "drug name",
      "alternative": "suggested alternative",
      "rationale": "reason for recommendation"
    }}
  ],
  "confidence_score": 0.95
}}
"""

    def _format_optional_patient(self, patient) -> str:
        if patient is None:
            return "- Not provided"

        lines = []
        if patient.fullName:
            lines.append(f"- Name: {patient.fullName}")
        if patient.gender:
            lines.append(f"- Gender: {patient.gender}")
        if patient.dob:
            lines.append(f"- Date of Birth: {patient.dob}")
        if patient.chiefComplaint:
            lines.append(f"- Chief Complaint: {patient.chiefComplaint}")
        if patient.primaryDiagnosis:
            lines.append(f"- Primary Diagnosis: {patient.primaryDiagnosis}")
        if patient.mrn:
            lines.append(f"- MRN: {patient.mrn}")
        return "\n".join(lines) if lines else "- Not provided"

    def _format_allergies(self, allergies) -> str:
        if not allergies:
            return "- None documented"
        formatted = []
        for i, allergy in enumerate(allergies, 1):
            allergy_type = allergy.allergy_type_description or "unspecified type"
            extra = []
            if allergy.status:
                extra.append(f"status={allergy.status}")
            if allergy.resolved is True:
                extra.append("resolved")
            suffix = f" ({', '.join(extra)})" if extra else ""
            formatted.append(f"{i}. {allergy.allergy_description} [{allergy_type}]{suffix}")
        return "\n".join(formatted)

    def _format_drugs(self, drugs) -> str:
        formatted = []
        for i, drug in enumerate(drugs, 1):
            formatted.append(f"{i}. {drug.drug_name}")
        return "\n".join(formatted)
