"""Unit tests for file format detection and text extraction (Step 0)."""
from unittest.mock import MagicMock

import pytest

from app.extraction.file_extractor import FileExtractor
from tests.fixtures.sample_data import (
    SAMPLE_CORRUPTED_PDF_BYTES,
    SAMPLE_CSV_BYTES,
    SAMPLE_DOCX_BYTES,
    SAMPLE_PDF_BYTES,
    SAMPLE_PNG_BYTES,
    SAMPLE_TXT_BYTES,
)


@pytest.fixture
def ai_client_stub():
    stub = MagicMock()
    stub.extract_text_from_image.return_value = "Transcribed image text"
    return stub


@pytest.fixture
def extractor(ai_client_stub):
    return FileExtractor(ai_client_stub)


class TestTxtExtraction:
    def test_extracts_plain_text(self, extractor):
        result = extractor.extract(SAMPLE_TXT_BYTES, "report.txt", "text/plain")
        assert result.detected_format == "txt"
        assert "LABORATORY REPORT" in result.text

    def test_empty_txt_raises(self, extractor):
        with pytest.raises(ValueError, match="empty"):
            extractor.extract(b"   ", "empty.txt", "text/plain")


class TestCsvExtraction:
    def test_extracts_csv_rows(self, extractor):
        result = extractor.extract(SAMPLE_CSV_BYTES, "labs.csv", "text/csv")
        assert result.detected_format == "csv"
        assert "WBC" in result.text
        assert "|" in result.text


class TestPdfExtraction:
    def test_extracts_pdf_text(self, extractor):
        result = extractor.extract(SAMPLE_PDF_BYTES, "report.pdf", "application/pdf")
        assert result.detected_format == "pdf"
        assert "Hello Patient Lab Report" in result.text

    def test_corrupted_pdf_raises(self, extractor):
        with pytest.raises(ValueError):
            extractor.extract(SAMPLE_CORRUPTED_PDF_BYTES, "bad.pdf", "application/pdf")


class TestDocxExtraction:
    def test_extracts_docx_text(self, extractor):
        result = extractor.extract(SAMPLE_DOCX_BYTES, "report.docx", None)
        assert result.detected_format == "docx"
        assert "LABORATORY REPORT" in result.text

    def test_corrupted_docx_raises(self, extractor):
        with pytest.raises(ValueError):
            extractor.extract(b"not a real docx", "bad.docx", None)


class TestImageExtraction:
    def test_extracts_image_via_vision(self, extractor, ai_client_stub):
        result = extractor.extract(SAMPLE_PNG_BYTES, "scan.png", "image/png")
        assert result.detected_format == "image"
        assert result.text == "Transcribed image text"
        ai_client_stub.extract_text_from_image.assert_called_once()

    def test_corrupted_image_raises(self, extractor):
        with pytest.raises(ValueError):
            extractor.extract(b"not an image", "scan.png", "image/png")


class TestFormatDetection:
    def test_unsupported_extension_raises(self, extractor):
        with pytest.raises(ValueError, match="Unsupported"):
            extractor.extract(b"data", "report.xyz", None)

    def test_empty_file_raises(self, extractor):
        with pytest.raises(ValueError, match="empty"):
            extractor.extract(b"", "report.txt", "text/plain")

    def test_content_type_takes_priority_over_extension(self, extractor):
        # .txt extension but PDF content-type -- content-type should win.
        result = extractor.extract(b"data", "report.txt", "application/csv")
        assert result.detected_format == "csv"
