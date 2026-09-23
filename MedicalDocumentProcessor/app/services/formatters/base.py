"""Base strategy interface for document-type formatters."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseDocumentFormatter(ABC):
    """Deterministically shapes the LLM's loose `extracted_fields` dict (Step 4) into
    a document-type-specific structured schema. Never calls the LLM itself -- keeps
    structured formatting testable without mocking network calls."""

    @abstractmethod
    def format(self, extracted_fields: Dict[str, Any], raw_text: str) -> Dict[str, Any]:
        """Return the structured_data dict for this document type."""
        raise NotImplementedError

    @staticmethod
    def _text(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
