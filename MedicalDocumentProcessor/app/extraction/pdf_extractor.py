"""PDF text extraction (existing repo dependency: pypdf, already used by
MedicalGuidelineValidation)."""
from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError

MIN_EXTRACTED_TEXT_CHARS = 20


def extract_pdf_text(file_bytes: bytes) -> str:
    """Extract text from a PDF's pages.

    Raises:
        ValueError: If the PDF is corrupted/unreadable, or has no extractable text
            (e.g. a scanned/image-only PDF -- out of scope for v1, see README).
    """
    try:
        reader = PdfReader(BytesIO(file_bytes))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as exc:  # noqa: BLE001
                raise ValueError("PDF is password-protected and could not be decrypted") from exc
        pages_text = [page.extract_text() or "" for page in reader.pages]
    except PdfReadError as exc:
        raise ValueError("Unreadable or corrupted PDF file") from exc
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Unreadable or corrupted PDF file: {exc}") from exc

    text = "\n".join(page.strip() for page in pages_text if page.strip())
    if len(text.strip()) < MIN_EXTRACTED_TEXT_CHARS:
        raise ValueError(
            "No extractable text found in PDF -- possibly a scanned/image-only PDF, "
            "which is not supported in this version (only JPG/PNG scans are OCR'd)"
        )
    return text
