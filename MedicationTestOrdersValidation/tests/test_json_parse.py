import json

import pytest

from services.medication_tests_validation_service import _parse_json_object


VALID_PAYLOAD = {
    "quick_summary": {
        "overall_status": "CONTRAINDICATED",
        "top_priority": "Penicillin allergy conflict",
    },
    "detailed_validations": [],
    "recommended_alternatives": [],
    "confidence_score": 0.9,
}


def test_parse_plain_json():
    assert _parse_json_object(json.dumps(VALID_PAYLOAD))["quick_summary"]["overall_status"] == "CONTRAINDICATED"


def test_parse_think_then_json():
    raw = "<think>the patient is allergic</think>\n" + json.dumps(VALID_PAYLOAD)
    assert _parse_json_object(raw)["confidence_score"] == 0.9


def test_parse_markdown_fence():
    raw = "```json\n" + json.dumps(VALID_PAYLOAD) + "\n```"
    assert _parse_json_object(raw)["quick_summary"]["overall_status"] == "CONTRAINDICATED"


def test_parse_preamble_then_object():
    raw = "Here is the validation result:\n" + json.dumps(VALID_PAYLOAD) + "\nThanks."
    assert _parse_json_object(raw)["quick_summary"]["top_priority"] == "Penicillin allergy conflict"


def test_parse_unclosed_think_before_json():
    raw = "<think>still reasoning\n" + json.dumps(VALID_PAYLOAD)
    assert _parse_json_object(raw)["confidence_score"] == 0.9


def test_parse_rejects_non_object():
    with pytest.raises(json.JSONDecodeError):
        _parse_json_object("[1, 2, 3]")
