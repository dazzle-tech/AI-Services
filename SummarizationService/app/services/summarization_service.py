"""Service layer for clinical summary generation."""
import logging
import re
from typing import Dict, Any, Set
from datetime import datetime

from app.models.schemas import SummaryRequest, SummaryResponse
from app.ai.client import AIClient
from app.core.config import settings

logger = logging.getLogger(__name__)

_NUMBER_RE = re.compile(r"\d+(?:[./]\d+)*%?")

# Categories the model has no business mentioning unless the corresponding
# input field was non-empty. Maps a detectable phrase pattern -> the
# patient_data field that must be present to justify it.
_CATEGORY_PHRASE_MAP = {
    "Symptoms": [r"\bsymptoms?\b", r"\bpresents? with\b", r"\bcomplains? of\b"],
    "Medications": [r"\bmedications?\b", r"\bon \w+ \d", r"\bmg\b", r"\bprescribed\b"],
    "Surgeries": [r"\bsurgery\b", r"\bsurgical\b", r"\boperation\b"],
    "Allergies": [r"\ballerg"],
    "Medical_Warnings": [r"\bwarning\b", r"\bcontraindicat"],
    "Problems": [r"\bcomorbidit", r"\bfamily history\b", r"\bhistory of\b"],
    "Vitals": [r"\bvital signs?\b", r"\bblood pressure\b", r"\bheart rate\b", r"\btemperature\b"],
    "Lab_Results": [r"\blab (results?|values?)\b", r"\bhba1c\b", r"\bcreatinine\b", r"\bglucose\b"],
}

# Fields that only make sense to check via demographics (never absent)
_ALWAYS_PRESENT_FIELDS = {"Age", "Gender", "Diagnosis"}


def _extract_numbers(text: str) -> Set[str]:
    """Extract numeric tokens (e.g. '135/82', '8.2%', '148') from a string."""
    return set(_NUMBER_RE.findall(text))


def _flatten_input_text(patient_data: Dict[str, Any]) -> str:
    """Flatten the patient data dict into one string to source allowed numbers from."""
    return " ".join(str(v) for v in _iter_values(patient_data))


def _iter_values(obj: Any):
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _iter_values(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _iter_values(v)
    else:
        yield obj


def find_hallucinated_numbers(patient_data: Dict[str, Any], summary: str) -> Set[str]:
    """
    Return the set of numeric tokens present in the generated summary but not
    present anywhere in the source patient data. A non-empty result strongly
    suggests the model fabricated vitals, labs, dosages, etc.
    """
    allowed = _extract_numbers(_flatten_input_text(patient_data))
    produced = _extract_numbers(summary)
    return produced - allowed


def find_hallucinated_categories(patient_data: Dict[str, Any], summary: str) -> Set[str]:
    """
    Return the set of data categories (Symptoms, Medications, Vitals, etc.)
    that the summary appears to reference via characteristic phrasing, even
    though that category was empty in the source data. Catches qualitative
    fabrication (e.g. an invented "family history of X") that the numeric
    guard can't see.
    """
    flagged = set()
    summary_lower = summary.lower()
    for field, patterns in _CATEGORY_PHRASE_MAP.items():
        field_value = patient_data.get(field)
        if field_value:  # category genuinely present in input, nothing to flag
            continue
        for pattern in patterns:
            if re.search(pattern, summary_lower):
                flagged.add(field)
                break
    return flagged


def is_sparse_input(patient_data: Dict[str, Any]) -> bool:
    """True if only demographics/diagnosis were provided - i.e. every other
    clinical field is empty. There is nothing for a model to synthesize here,
    so we skip the LLM entirely and use a deterministic template instead."""
    other_fields = [k for k in patient_data.keys() if k not in _ALWAYS_PRESENT_FIELDS]
    return not any(patient_data.get(k) for k in other_fields)


def build_sparse_summary(patient_data: Dict[str, Any]) -> str:
    """Deterministic, hallucination-free summary for demographics-only input."""
    age = patient_data.get("Age", "unknown age")
    gender = patient_data.get("Gender", "patient")
    diagnosis = patient_data.get("Diagnosis", "an unspecified condition")
    return f"A {age} {gender} with {diagnosis}. No further clinical detail was provided."


class SummarizationService:
    """Service for handling clinical summary generation requests."""
    
    def __init__(self):
        """Initialize service with AI client."""
        self.ai_client = AIClient()
    
    def process_request(self, request: SummaryRequest) -> SummaryResponse:
        """
        Process a summary generation request.
        
        Args:
            request: Summary request with patient data
            
        Returns:
            Summary response with generated clinical summary
        """
        try:
            request_id = request.request_id or f"req_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            logger.info(f"Processing summary request {request_id}")
            
            # Convert patient data to dict
            patient_data_dict = request.patient_data.dict()
            
            # Log input data (for debugging)
            logger.info(f"Patient data input: {patient_data_dict}")

            # Step 1: Generate summary.
            # For demographics-only input there is nothing for the model to
            # synthesize, and small/local models reliably pad such cases with
            # fabricated detail (invented history, vitals, meds) - so we skip
            # the LLM entirely and use a deterministic template instead.
            if is_sparse_input(patient_data_dict):
                logger.info(
                    "Sparse input detected for request %s - using deterministic "
                    "template instead of calling the model", request_id
                )
                summary = build_sparse_summary(patient_data_dict)
                suspect_numbers: Set[str] = set()
                suspect_categories: Set[str] = set()
            else:
                logger.info("Generating clinical summary with OpenAI...")
                summary = self.ai_client.generate_summary(patient_data_dict)
                logger.info(f"Summary generated successfully for request {request_id}")

                # Step 1.5: Guard against fabricated clinical detail that
                # doesn't trace back to anything in the source data.
                suspect_numbers = find_hallucinated_numbers(patient_data_dict, summary)
                suspect_categories = find_hallucinated_categories(patient_data_dict, summary)
                if suspect_numbers:
                    logger.warning(
                        "Possible hallucination in request %s: summary contains numeric "
                        "values not found in source data: %s",
                        request_id, sorted(suspect_numbers)
                    )
                if suspect_categories:
                    logger.warning(
                        "Possible hallucination in request %s: summary references "
                        "categories with no supporting input data: %s",
                        request_id, sorted(suspect_categories)
                    )

            # Step 2: Build response with enhanced metadata
            response = SummaryResponse(
                request_id=request_id,
                ClinicalSummary=summary,
                processing_metadata={
                    "model": settings.openai_model,
                    "timestamp": datetime.now().isoformat(),
                    "input_fields_count": len([k for k, v in patient_data_dict.items() if v]),
                    "summary_length": len(summary),
                    "provider": "openai",
                    "api_version": "v1",
                    "possible_hallucination": bool(suspect_numbers or suspect_categories),
                    "unverified_values": sorted(suspect_numbers) if suspect_numbers else [],
                    "unverified_categories": sorted(suspect_categories) if suspect_categories else []
                }
            )
            
            return response
            
        except ValueError as e:
            logger.error(f"Validation error for request {request.request_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error processing request {request.request_id}: {e}")
            raise ValueError(f"Summary generation failed: {str(e)}")

