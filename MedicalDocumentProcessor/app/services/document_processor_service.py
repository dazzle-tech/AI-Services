"""Orchestrates the full validation -> relevance -> translation -> formatting
pipeline and assembles the single response envelope, regardless of where the
pipeline stops."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

from app.ai.client import AIClient
from app.core.config import settings
from app.extraction.file_extractor import FileExtractor
from app.models.schemas import (
    ExistingDocumentSummary,
    PatientInfo,
    ProcessDocumentResponse,
)
from app.services.formatting_service import FormattingService
from app.services.relevance_service import RelevanceService
from app.services.translation_service import TranslationService
from app.services.validation_service import ValidationService

logger = logging.getLogger(__name__)


class DocumentProcessorService:
    def __init__(self) -> None:
        self.ai_client = AIClient()
        self.file_extractor = FileExtractor(self.ai_client)
        self.validation_service = ValidationService(self.ai_client)
        self.relevance_service = RelevanceService(self.ai_client)
        self.translation_service = TranslationService(self.ai_client)
        self.formatting_service = FormattingService(self.ai_client)

    def process(
        self,
        file_bytes: bytes,
        filename: Optional[str],
        content_type: Optional[str],
        patient: PatientInfo,
        translate: bool,
        target_language: str,
        existing_documents: List[ExistingDocumentSummary],
        request_id: Optional[str] = None,
    ) -> ProcessDocumentResponse:
        request_id = request_id or f"req_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        logger.info("Processing document request %s (filename=%s)", request_id, filename)

        # Step 0 -- file & format validation (readability, not corrupted).
        try:
            extraction = self.file_extractor.extract(file_bytes, filename, content_type)
        except ValueError as exc:
            logger.info("Request %s failed file extraction: %s", request_id, exc)
            return self._response(
                status="invalid",
                reason=str(exc),
                raw_extracted_text="",
                request_id=request_id,
                metadata={"stage": "file_extraction"},
            )

        raw_text = extraction.text

        # Step 1 -- patient-match validation.
        validation = self.validation_service.validate(patient, raw_text)
        if not validation.is_valid:
            logger.info("Request %s failed patient-match validation: %s", request_id, validation.reason)
            return self._response(
                status="invalid",
                reason=validation.reason,
                raw_extracted_text=raw_text,
                request_id=request_id,
                metadata={
                    "stage": "patient_validation",
                    "detected_format": extraction.detected_format,
                    "mismatches": validation.mismatches,
                    "extracted_patient_signals": validation.extracted_patient_signals,
                },
            )

        # Step 2 -- relevance check.
        relevance = self.relevance_service.check(raw_text, existing_documents)
        if not relevance.is_relevant:
            logger.info("Request %s marked irrelevant: %s", request_id, relevance.reason)
            return self._response(
                status="irrelevant",
                reason=relevance.reason,
                raw_extracted_text=raw_text,
                request_id=request_id,
                metadata={
                    "stage": "relevance_check",
                    "detected_format": extraction.detected_format,
                    "apparent_document_type": relevance.apparent_document_type,
                    "document_date": relevance.document_date,
                    "relevance_window_days": relevance.relevance_window_days,
                },
            )

        # Step 3 -- language detection + conditional translation.
        translation = self.translation_service.process(raw_text, translate, target_language)
        working_text = translation.translated_text if translation.translated else raw_text

        # Step 4 -- document-type classification + structured formatting.
        document_type, structured_data = self.formatting_service.format(working_text)

        logger.info("Request %s processed successfully as document_type=%s", request_id, document_type)
        return self._response(
            status="processed",
            reason=None,
            raw_extracted_text=raw_text,
            request_id=request_id,
            detected_language=translation.detected_language,
            translated=translation.translated,
            document_type=document_type,
            structured_data=structured_data,
            metadata={
                "stage": "completed",
                "detected_format": extraction.detected_format,
                "model": settings.openai_model,
                "target_language": target_language,
            },
        )

    @staticmethod
    def _response(
        status: str,
        reason: Optional[str],
        raw_extracted_text: str,
        request_id: str,
        metadata: dict,
        detected_language: Optional[str] = None,
        translated: bool = False,
        document_type: Optional[str] = None,
        structured_data: Optional[dict] = None,
    ) -> ProcessDocumentResponse:
        return ProcessDocumentResponse(
            status=status,
            reason=reason,
            detected_language=detected_language,
            translated=translated,
            document_type=document_type,
            structured_data=structured_data,
            raw_extracted_text=raw_extracted_text,
            request_id=request_id,
            processing_metadata={
                "timestamp": datetime.now().isoformat(),
                **metadata,
            },
        )
