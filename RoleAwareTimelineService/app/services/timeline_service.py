"""Orchestrate timeline, summary, and role highlights inside one request."""
import json
import logging
from datetime import datetime, timezone

from app.ai.client import AIClient
from app.ai.guardrails import (
    clean_text,
    combine_gaps,
    prepare_highlights,
    timeline_corpus,
)
from app.core.config import settings
from app.models.schemas import (
    ProcessingMetadata,
    RoleTimelineRequest,
    RoleTimelineResponse,
)
from app.services.timeline_builder import (
    assign_ids,
    backfill_missing,
    clean_drafts,
    merge_events,
    sort_events,
)

logger = logging.getLogger(__name__)


class TimelineService:
    """Generate the shared timeline and summary, then highlights for one role."""

    def __init__(self):
        """Initialize the OpenAI client."""
        self.ai_client = AIClient()

    def process_request(self, request: RoleTimelineRequest) -> RoleTimelineResponse:
        """Run the three generation steps and apply fidelity checks."""
        patient = request.patient_data.model_dump(exclude_none=True)
        self._check_input_length(patient)
        request_id = request.request_id or f"req_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        logger.info("Processing role timeline %s for %s", request_id, request.viewer_role)

        drafts = self.ai_client.generate_timeline(patient)
        events = clean_drafts(drafts, patient)
        events = backfill_missing(events, patient)
        events = assign_ids(sort_events(merge_events(events)))

        summary = self.ai_client.generate_summary(
            events,
            patient.get("age"),
            patient.get("gender"),
        )
        allowed_corpus = timeline_corpus(events, patient.get("age"), patient.get("gender"))
        summary = clean_text(summary, allowed_corpus)
        if not summary:
            raise ValueError("Clinical summary was empty after fidelity checks")

        highlights, model_gaps = self.ai_client.generate_highlights(events, request.viewer_role)
        highlights, moved_gaps = prepare_highlights(
            highlights,
            events,
            request.viewer_role,
            allowed_corpus,
        )
        gaps = combine_gaps([*model_gaps, *moved_gaps], patient, request.viewer_role)

        return RoleTimelineResponse(
            request_id=request_id,
            timeline=events,
            clinical_summary=summary,
            role_highlights=highlights,
            not_documented=gaps,
            processing_metadata=ProcessingMetadata(
                model=settings.openai_model,
                timestamp=datetime.now(timezone.utc).isoformat(),
                event_count=len(events),
                viewer_role=request.viewer_role,
            ),
        )

    def _check_input_length(self, patient: dict) -> None:
        """Reject a chart extract that exceeds the configured limit."""
        if len(json.dumps(patient, ensure_ascii=True)) > settings.max_input_length:
            raise ValueError("Patient data exceeds the configured input length")
