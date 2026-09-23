"""Formatter registry -- strategy pattern keyed by DocumentType.

New document types can be supported by adding a formatter module below and
registering it here; the pipeline logic (formatting_service.py) never changes.
"""
from typing import Any, Dict

from app.models.schemas import DocumentType
from app.services.formatters.base import BaseDocumentFormatter
from app.services.formatters.clinical_note_formatter import ClinicalNoteFormatter
from app.services.formatters.generic_formatter import GenericFormatter
from app.services.formatters.lab_result_formatter import LabResultFormatter
from app.services.formatters.prescription_formatter import PrescriptionFormatter
from app.services.formatters.radiology_report_formatter import RadiologyReportFormatter

_GENERIC_FORMATTER = GenericFormatter()

FORMATTER_REGISTRY: Dict[DocumentType, BaseDocumentFormatter] = {
    DocumentType.LAB_RESULT: LabResultFormatter(),
    DocumentType.RADIOLOGY_REPORT: RadiologyReportFormatter(),
    DocumentType.IMAGING_REPORT: RadiologyReportFormatter(),
    DocumentType.PRESCRIPTION: PrescriptionFormatter(),
    DocumentType.CLINICAL_NOTE: ClinicalNoteFormatter(),
    DocumentType.PHYSICIAN_NOTE: ClinicalNoteFormatter(),
}


def get_formatter(document_type: DocumentType) -> BaseDocumentFormatter:
    """Look up the formatter for a document type, falling back to the generic
    formatter for unregistered/unknown types -- mirrors this repo's own
    generic.html fallback-for-unknown convention."""
    return FORMATTER_REGISTRY.get(document_type, _GENERIC_FORMATTER)


def format_document(
    document_type: DocumentType, extracted_fields: Dict[str, Any], raw_text: str
) -> Dict[str, Any]:
    formatter = get_formatter(document_type)
    return formatter.format(extracted_fields, raw_text)
