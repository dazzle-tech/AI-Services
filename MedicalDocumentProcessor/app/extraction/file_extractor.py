"""Format detection + dispatch for uploaded medical documents."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from app.extraction.csv_extractor import extract_csv_text
from app.extraction.docx_extractor import extract_docx_text
from app.extraction.image_extractor import extract_image_text
from app.extraction.pdf_extractor import extract_pdf_text

logger = logging.getLogger(__name__)

_EXTENSION_FORMAT_MAP = {
    "pdf": "pdf",
    "docx": "docx",
    "doc": "docx",
    "txt": "txt",
    "text": "txt",
    "csv": "csv",
    "jpg": "image",
    "jpeg": "image",
    "png": "image",
}

_CONTENT_TYPE_FORMAT_MAP = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/msword": "docx",
    "text/plain": "txt",
    "text/csv": "csv",
    "application/csv": "csv",
    "image/jpeg": "image",
    "image/jpg": "image",
    "image/png": "image",
}

SUPPORTED_FORMATS = {"pdf", "docx", "txt", "csv", "image"}


@dataclass(frozen=True)
class ExtractedDocument:
    text: str
    detected_format: str


def _detect_format(filename: str | None, content_type: str | None) -> str:
    if content_type:
        fmt = _CONTENT_TYPE_FORMAT_MAP.get(content_type.lower().split(";")[0].strip())
        if fmt:
            return fmt

    if filename and "." in filename:
        ext = filename.rsplit(".", 1)[-1].lower().strip()
        fmt = _EXTENSION_FORMAT_MAP.get(ext)
        if fmt:
            return fmt

    raise ValueError(
        f"Unsupported or undetectable file type (filename={filename!r}, "
        f"content_type={content_type!r}). Supported formats: PDF, DOCX, TXT, CSV, JPG/PNG."
    )


class FileExtractor:
    """Detects the uploaded file's format and extracts its text content."""

    def __init__(self, ai_client) -> None:
        # Only needed for the "image" format (vision OCR path).
        self._ai_client = ai_client

    def extract(
        self,
        file_bytes: bytes,
        filename: str | None,
        content_type: str | None,
    ) -> ExtractedDocument:
        if not file_bytes:
            raise ValueError("Uploaded file is empty")

        detected_format = _detect_format(filename, content_type)
        logger.info(
            "Extracting text: filename=%s content_type=%s detected_format=%s size=%d bytes",
            filename, content_type, detected_format, len(file_bytes),
        )

        if detected_format == "pdf":
            text = extract_pdf_text(file_bytes)
        elif detected_format == "docx":
            text = extract_docx_text(file_bytes)
        elif detected_format == "csv":
            text = extract_csv_text(file_bytes)
        elif detected_format == "image":
            text = extract_image_text(file_bytes, content_type, self._ai_client)
        elif detected_format == "txt":
            text = self._extract_txt(file_bytes)
        else:  # pragma: no cover - guarded by _detect_format
            raise ValueError(f"Unsupported file format: {detected_format}")

        return ExtractedDocument(text=text, detected_format=detected_format)

    @staticmethod
    def _extract_txt(file_bytes: bytes) -> str:
        try:
            text = file_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                text = file_bytes.decode("latin-1")
            except Exception as exc:  # noqa: BLE001
                raise ValueError(f"Unreadable or corrupted text file: {exc}") from exc

        if not text.strip():
            raise ValueError("Text file is empty")
        return text
