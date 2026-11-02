"""Step 2: relevance check.

The document type comes from the caller. The model proposes a document date and a
relevance decision. A date older than that type's configured window is irrelevant
whether or not the model says so.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from app.ai.client import AIClient
from app.core.config import settings
from app.models.schemas import ExistingDocumentSummary, RelevanceOutcome

_DATE_FORMATS = (
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%m/%d/%Y",
    "%B %d, %Y",
    "%b %d, %Y",
    "%d %B %Y",
    "%d %b %Y",
)
_LABELED_DATE = re.compile(
    r"(?:test date|study date|report date|collection date|collected|date of service|"
    r"note date|prescription date|(?<!birth )date)\s*[:\-]\s*"
    r"(\d{4}-\d{2}-\d{2}|\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|"
    r"[A-Za-z]{3,9}\s+\d{1,2},\s+\d{4}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})",
    re.IGNORECASE,
)

logger = logging.getLogger(__name__)


class RelevanceService:
    def __init__(self, ai_client: AIClient) -> None:
        self.ai_client = ai_client

    def check(
        self,
        extracted_text: str,
        existing_documents: List[ExistingDocumentSummary],
        document_type: str,
    ) -> RelevanceOutcome:
        relevance_windows_days = settings.relevance_windows_days
        raw = self.ai_client.classify_relevance(
            extracted_text,
            relevance_windows_days,
            [doc.model_dump() for doc in existing_documents],
            document_type,
        )
        return self._normalize(raw, relevance_windows_days, document_type, extracted_text, existing_documents)

    def _normalize(
        self,
        raw: Dict[str, Any],
        relevance_windows_days: Dict[str, int],
        document_type: str,
        extracted_text: str,
        existing_documents: List[ExistingDocumentSummary],
    ) -> RelevanceOutcome:
        apparent_type = document_type
        document_date = self._text(raw.get("document_date"))
        is_relevant = bool(raw.get("is_relevant", True))
        reason = self._text(raw.get("reason"))

        window_days = relevance_windows_days.get(
            document_type, relevance_windows_days.get("other")
        )
        parsed = self._parse_date(document_date) if document_date else None
        labeled = self._labeled_date(extracted_text)
        if parsed is None:
            parsed = labeled
        elif (
            labeled is not None
            and window_days is not None
            and (date.today() - labeled).days > window_days
            and (date.today() - labeled).days > (date.today() - parsed).days
        ):
            # The date printed on the document is past the window. Do not keep a
            # newer date proposed by the model.
            parsed = labeled

        if parsed is not None and window_days is not None and (date.today() - parsed).days > window_days:
            is_relevant = False
            document_date = parsed.isoformat()
            reason = (
                f"{document_type} dated {parsed.isoformat()} is outside the "
                f"{window_days}-day relevance window."
            )
        elif is_relevant and parsed is not None:
            newer = self._newer_existing(existing_documents, document_type, parsed)
            if newer is not None:
                is_relevant = False
                reason = f"Superseded by a newer {document_type} dated {newer.isoformat()}."

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

    @classmethod
    def _labeled_date(cls, text: str) -> Optional[date]:
        for match in _LABELED_DATE.finditer(text or ""):
            line_start = text.rfind("\n", 0, match.start()) + 1
            line_end = text.find("\n", match.end())
            line = text[line_start: line_end if line_end != -1 else None]
            if "birth" in line.lower():
                continue
            parsed = cls._parse_date(match.group(1))
            if parsed is not None:
                return parsed
        return None

    @classmethod
    def _newer_existing(
        cls,
        existing_documents: List[ExistingDocumentSummary],
        document_type: str,
        document_date: date,
    ) -> Optional[date]:
        newer: Optional[date] = None
        for existing in existing_documents:
            if (existing.document_type or "").strip().lower() != document_type:
                continue
            parsed = cls._parse_date(existing.document_date)
            if parsed is not None and parsed > document_date and (newer is None or parsed > newer):
                newer = parsed
        return newer

    @staticmethod
    def _parse_date(value: Optional[str]) -> Optional[date]:
        if not value:
            return None
        text = str(value).strip()
        if len(text) >= 10:
            try:
                return date.fromisoformat(text[:10])
            except ValueError:
                pass
        for fmt in _DATE_FORMATS:
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        return None
