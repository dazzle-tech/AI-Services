"""Service layer for patient timeline generation."""
import logging
from datetime import datetime
from typing import Dict, List, Tuple

from app.ai.client import AIClient
from app.core.config import settings
from app.models.schemas import (
    ProcessingMetadata,
    TimelineEvent,
    TimelineRequest,
    TimelineResponse,
)

logger = logging.getLogger(__name__)


class TimelineService:
    """Service for handling patient timeline generation requests."""

    def __init__(self):
        """Initialize service with AI client."""
        self.ai_client = AIClient()

    def process_request(self, request: TimelineRequest) -> TimelineResponse:
        """
        Process a timeline generation request.

        Args:
            request: Timeline request with patient data

        Returns:
            Timeline response with generated patient timeline
        """
        try:
            request_id = request.request_id or f"req_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            logger.info(f"Processing timeline request {request_id}")

            patient_data_dict = request.patient_data.model_dump()
            logger.info(f"Patient timeline input: {patient_data_dict}")

            logger.info("Generating patient timeline with OpenAI...")
            timeline = self.ai_client.generate_timeline(patient_data_dict)

            deduplicated_timeline = self._merge_duplicate_events(timeline)
            sorted_timeline = self._sort_events(deduplicated_timeline)

            response = TimelineResponse(
                request_id=request_id,
                timeline=sorted_timeline,
                summary="Chronological timeline generated successfully.",
                processing_metadata=ProcessingMetadata(
                    model=settings.openai_model,
                    timestamp=datetime.now().isoformat(),
                    input_fields_count=self._count_populated_fields(patient_data_dict),
                    timeline_event_count=len(sorted_timeline)
                )
            )

            return response

        except ValueError as e:
            logger.error(f"Validation error for request {request.request_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error processing request {request.request_id}: {e}")
            raise ValueError(f"Timeline generation failed: {str(e)}")

    def _count_populated_fields(self, patient_data_dict: Dict[str, object]) -> int:
        """Count populated top-level patient data fields."""
        return len([
            key for key, value in patient_data_dict.items()
            if value not in (None, "", [], {})
        ])

    def _merge_duplicate_events(self, timeline: List[TimelineEvent]) -> List[TimelineEvent]:
        """Merge duplicate timeline events and preserve traceability."""
        merged: Dict[Tuple[str, str, str], TimelineEvent] = {}

        for event in timeline:
            key = (
                event.date.strip(),
                event.event_type,
                self._normalize_key(event.title),
            )

            if key not in merged:
                merged[key] = event
                continue

            existing = merged[key]
            existing.description = self._merge_text(existing.description, event.description)
            existing.source = self._merge_sources(existing.source, event.source)
            existing.clinical_importance = self._higher_importance(
                existing.clinical_importance,
                event.clinical_importance
            )

        return list(merged.values())

    def _sort_events(self, timeline: List[TimelineEvent]) -> List[TimelineEvent]:
        """Sort events by date ascending."""
        return sorted(
            timeline,
            key=lambda event: (
                self._parse_sort_date(event.date),
                event.event_type,
                event.title.lower(),
            )
        )

    def _parse_sort_date(self, raw_date: str):
        """Parse ISO-like dates for sorting."""
        normalized = raw_date.strip()
        try:
            return datetime.fromisoformat(normalized.replace("Z", "+00:00"))
        except ValueError:
            try:
                return datetime.strptime(normalized, "%Y-%m-%d")
            except ValueError:
                return datetime.max

    def _normalize_key(self, value: str) -> str:
        """Normalize text for duplicate detection."""
        return " ".join(value.lower().split())

    def _merge_text(self, existing_text: str, new_text: str) -> str:
        """Merge descriptions without duplicating content."""
        if self._normalize_key(existing_text) == self._normalize_key(new_text):
            return existing_text
        return f"{existing_text} {new_text}".strip()

    def _merge_sources(self, existing_source: str, new_source: str) -> str:
        """Merge event source strings into a stable traceability field."""
        source_values = {part.strip() for part in existing_source.split(",") if part.strip()}
        source_values.update({part.strip() for part in new_source.split(",") if part.strip()})
        return ", ".join(sorted(source_values))

    def _higher_importance(self, left: str, right: str) -> str:
        """Return the higher clinical importance level."""
        ranking = {"high": 3, "medium": 2, "low": 1}
        return left if ranking[left] >= ranking[right] else right
