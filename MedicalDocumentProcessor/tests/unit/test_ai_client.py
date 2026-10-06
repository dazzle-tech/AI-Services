"""Unit tests for AIClient JSON parsing and truncated-output recovery."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.ai.client import AIClient


class TestParseJson:
    def test_parses_plain_object(self):
        data = AIClient._parse_json('{"document_type": "lab_result"}', "test")
        assert data["document_type"] == "lab_result"

    def test_strips_markdown_fences(self):
        raw = '```json\n{"document_type": "prescription"}\n```'
        data = AIClient._parse_json(raw, "test")
        assert data["document_type"] == "prescription"

    def test_extracts_object_from_surrounding_text(self):
        raw = 'Here you go:\n{"document_type": "clinical_note"}\nThanks'
        data = AIClient._parse_json(raw, "test")
        assert data["document_type"] == "clinical_note"

    def test_rejects_non_object(self):
        with pytest.raises(ValueError, match="not a JSON object"):
            AIClient._parse_json("[1, 2, 3]", "test")


class TestRepairTruncatedJson:
    def test_closes_truncated_results_array(self):
        raw = (
            '{"document_type": "lab_result", "extracted_fields": '
            '{"test_date": "2026-08-01", "results": ['
            '{"test_name": "WBC", "value": "11.2"},'
            '{"test_name": "Hemoglobin", "value": "13.'
        )
        repaired = AIClient._repair_truncated_json(raw)
        assert repaired is not None
        assert repaired["document_type"] == "lab_result"
        assert repaired["extracted_fields"]["results"][0]["test_name"] == "WBC"

    def test_closes_unclosed_string(self):
        raw = '{"document_type": "radiology_report", "extracted_fields": {"findings": "Clear lungs'
        repaired = AIClient._repair_truncated_json(raw)
        assert repaired is not None
        assert repaired["document_type"] == "radiology_report"
        assert "Clear lungs" in repaired["extracted_fields"]["findings"]

    def test_returns_none_for_empty(self):
        assert AIClient._repair_truncated_json("") is None

    def test_looks_truncated_without_closing_brace(self):
        assert AIClient._looks_truncated('{"document_type": "lab_result"')
        assert not AIClient._looks_truncated('{"document_type": "lab_result"}')


class TestCallJsonTruncationRetry:
    def test_retries_truncated_json_with_higher_token_budget(self):
        client = object.__new__(AIClient)
        client.client = MagicMock()
        client.model = "gpt-4o"
        client.temperature = 0.1
        client.max_tokens = 2000
        client.max_retries = 1
        client.retry_delay = 0
        client.timeout = 30

        truncated = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content='{"document_type": "lab_result", "extracted_fields": {"results": ['
                    ),
                    finish_reason="length",
                )
            ],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=2000, total_tokens=2010),
        )
        complete = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content='{"document_type": "lab_result", "extracted_fields": {"results": []}}'
                    ),
                    finish_reason="stop",
                )
            ],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=40, total_tokens=50),
        )
        client.client.chat.completions.create.side_effect = [truncated, complete]

        with patch("app.ai.client.settings") as mock_settings:
            mock_settings.enable_usage_tracking = False
            result = client._call_json("classification + extraction", [{"role": "user", "content": "x"}], max_tokens=2000)

        assert result["document_type"] == "lab_result"
        assert client.client.chat.completions.create.call_count == 2
        second_kwargs = client.client.chat.completions.create.call_args_list[1].kwargs
        assert second_kwargs["max_tokens"] == 8000
