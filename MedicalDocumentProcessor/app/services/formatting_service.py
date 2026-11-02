"""Step 4: structured formatting for the caller-chosen document type.

The caller supplies the document type. The LLM extracts fields for that type (one call);
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

    def format(self, extracted_text: str, document_type: DocumentType) -> Tuple[str, Dict[str, Any]]:
        raw = self.ai_client.extract_fields(extracted_text, document_type.value)

        extracted_fields = raw.get("extracted_fields")
        if not isinstance(extracted_fields, dict):
            extracted_fields = {}

        structured_data = format_document(document_type, extracted_fields, extracted_text)
        structured_data["document_type"] = document_type.value
        return document_type.value, structured_data
