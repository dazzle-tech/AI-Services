"""Step 2: relevance check.

Runs its own independent classification of apparent document type + date (rather than
depending on Step 4's formal classification, which hasn't run yet in the pipeline order),
so this step stays self-contained and independently testable/debuggable, per the pipeline
design. Step 4 performs the authoritative classification for the final output.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.ai.client import AIClient
from app.core.config import settings
from app.models.schemas import ExistingDocumentSummary, RelevanceOutcome

logger = logging.getLogger(__name__)


class RelevanceService:
    def __init__(self, ai_client: AIClient) -> None:
        self.ai_client = ai_client

    def check(
        self,
        extracted_text: str,
        existing_documents: List[ExistingDocumentSummary],
    ) -> RelevanceOutcome:
        relevance_windows_days = settings.relevance_windows_days
        raw = self.ai_client.classify_relevance(
            extracted_text,
            relevance_windows_days,
            [doc.model_dump() for doc in existing_documents],
        )
        return self._normalize(raw, relevance_windows_days)

    def _normalize(
        self, raw: Dict[str, Any], relevance_windows_days: Dict[str, int]
    ) -> RelevanceOutcome:
        apparent_type = self._text(raw.get("apparent_document_type"))
        document_date = self._text(raw.get("document_date"))
        is_relevant = bool(raw.get("is_relevant", True))
        reason = self._text(raw.get("reason"))

        window_days: Optional[int] = None
        if apparent_type:
            window_days = relevance_windows_days.get(
                apparent_type.strip().lower(), relevance_windows_days.get("other")
            )

        if not is_relevant and not reason:
            reason = "Document was classified as not clinically relevant to the active record."

        return RelevanceOutcome(
            is_relevant=is_relevant,
            reason=reason,
            apparent_document_type=apparent_type,
            document_date=document_date,
            relevance_window_days=window_days,
        )

    @staticmethod
    def _text(value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
