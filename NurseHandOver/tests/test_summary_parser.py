"""
test_summary_parser.py
----------------------
Tests for summary_parser.py — validates that GPT output is correctly
parsed, validated, and that malformed responses are rejected cleanly.
No API calls made here.
"""

import json
import pytest

from app.services.summary_parser import parse_and_validate
from app.models.schemas import SBARSummary, Priority


class TestValidInput:
    def test_parses_critical_patient(self, valid_gpt_response_critical):
        result = parse_and_validate(valid_gpt_response_critical, "pt_001")
        assert isinstance(result, SBARSummary)
        assert result.patient_id == "pt_001"
        assert result.priority == Priority.critical

    def test_parses_stable_patient(self, valid_gpt_response_stable):
        result = parse_and_validate(valid_gpt_response_stable, "pt_003")
        assert isinstance(result, SBARSummary)
        assert result.patient_id == "pt_003"
        assert result.priority == Priority.stable

    def test_all_sbar_fields_populated(self, valid_gpt_response_critical):
        result = parse_and_validate(valid_gpt_response_critical, "pt_001")
        assert len(result.situation)      > 0
        assert len(result.background)     > 0
        assert len(result.assessment)     > 0
        assert len(result.recommendation) > 0

    def test_flags_are_list(self, valid_gpt_response_critical):
        result = parse_and_validate(valid_gpt_response_critical, "pt_001")
        assert isinstance(result.flags, list)
        assert len(result.flags) > 0

    def test_generated_at_is_set(self, valid_gpt_response_critical):
        result = parse_and_validate(valid_gpt_response_critical, "pt_001")
        assert result.generated_at is not None

    def test_patient_id_overrides_gpt_value(self, valid_gpt_response_critical):
        """
        Even if GPT hallucinates a different patient_id, the parser
        must enforce the correct one passed by the caller.
        """
        result = parse_and_validate(valid_gpt_response_critical, "FORCED_ID")
        assert result.patient_id == "FORCED_ID"

    def test_empty_flags_allowed(self, valid_gpt_response_stable):
        """A patient with no outstanding items may have an empty flags list."""
        data = json.loads(valid_gpt_response_stable)
        data["flags"] = []
        result = parse_and_validate(json.dumps(data), "pt_003")
        assert result.flags == []


class TestInvalidInput:
    def test_raises_on_invalid_json(self):
        with pytest.raises(ValueError, match="invalid JSON"):
            parse_and_validate("this is not json {{{", "pt_001")

    def test_raises_on_missing_required_field(self):
        """Missing 'situation' should cause a schema validation error."""
        incomplete = json.dumps({
            "patient_id": "pt_001",
            "priority": "critical",
            # situation is missing
            "background": "Some background.",
            "assessment": "Some assessment.",
            "recommendation": "1. Do something.",
            "flags": [],
        })
        with pytest.raises(ValueError, match="schema validation"):
            parse_and_validate(incomplete, "pt_001")

    def test_raises_on_invalid_priority_value(self):
        """Priority must be one of critical/watch/stable."""
        bad_priority = json.dumps({
            "patient_id": "pt_001",
            "priority": "unknown_level",
            "situation": "S",
            "background": "B",
            "assessment": "A",
            "recommendation": "R",
            "flags": [],
        })
        with pytest.raises(ValueError, match="schema validation"):
            parse_and_validate(bad_priority, "pt_001")

    def test_raises_on_empty_string(self):
        with pytest.raises(ValueError, match="invalid JSON"):
            parse_and_validate("", "pt_001")

    def test_raises_on_json_array_instead_of_object(self):
        """GPT should return an object, not an array."""
        with pytest.raises(ValueError):
            parse_and_validate('["not", "an", "object"]', "pt_001")
