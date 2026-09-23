"""Step 4: document-type classification + structured formatting.

The LLM classifies the document type and performs loose field extraction (one call);
the formatter registry (pure Python, no LLM call) then deterministically shapes those
raw fields into the document type's strict structured schema. New document types are
added by registering a formatter, without touching this orchestration logic.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Tuple

from app.ai.client import AIClient
from app.models.schemas import DocumentType
from app.services.formatters import format_document

logger = logging.getLogger(__name__)


class FormattingService:
    def __init__(self, ai_client: AIClient) -> None:
        self.ai_client = ai_client

    def format(self, extracted_text: str) -> Tuple[str, Dict[str, Any]]:
        raw = self.ai_client.classify_and_extract(extracted_text)

        document_type = DocumentType.coerce(raw.get("document_type"))
        extracted_fields = raw.get("extracted_fields")
        if not isinstance(extracted_fields, dict):
            extracted_fields = {}

        structured_data = format_document(document_type, extracted_fields, extracted_text)
        return document_type.value, structured_data
