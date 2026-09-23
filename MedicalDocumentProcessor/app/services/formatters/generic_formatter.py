"""Fallback formatter for document types without a dedicated strategy (DocumentType.OTHER
or any unrecognized classification) -- mirrors this repo's own generic.html
fallback-for-unknown-service convention."""
from __future__ import annotations

from typing import Any, Dict

from app.models.schemas import GenericDocumentData
from app.services.formatters.base import BaseDocumentFormatter

MAX_GENERIC_CONTENT_CHARS = 20000


class GenericFormatter(BaseDocumentFormatter):
    def format(self, extracted_fields: Dict[str, Any], raw_text: str) -> Dict[str, Any]:
        summary = self._text(extracted_fields.get("summary")) if extracted_fields else None
        content = raw_text.strip()
        if len(content) > MAX_GENERIC_CONTENT_CHARS:
            content = content[:MAX_GENERIC_CONTENT_CHARS] + "...[truncated]"

        data = GenericDocumentData(document_type="other", summary=summary, content=content)
        return data.model_dump()
