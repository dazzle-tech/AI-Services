"""Unit tests for response validator."""

from src.core.response_validator import ResponseValidator


def test_fix_response_strips_invalid_top_level_keys():
    validator = ResponseValidator()
    response = {
        "qa_method": "direct_qa",
        "overall_score": 100,
        "summary": "Test",
        "parsed_report": {
            "format": "text",
            "structure_used": "standard",
            "content": {},
            "unmapped_content": [],
        },
        "errors": [],
        "missing_items": [],
        "consistency": True,
        "safety": True,
    }

    fixed = validator.fix_response(response)

    assert "consistency" not in fixed
    assert "safety" not in fixed
    assert "inconsistencies" in fixed
    assert "recommended_corrections" in fixed


def test_fix_parsed_report_adds_unmapped_content_and_removes_misplaced_sections():
    validator = ResponseValidator()
    response = {
        "qa_method": "direct_qa",
        "overall_score": 100,
        "summary": "Test",
        "parsed_report": {
            "format": "text",
            "structure_used": "standard",
            "content": {
                "medications": {"discharge_medications": [{"name": "Aspirin"}]},
            },
            "allergies": {"allergies": ["NKDA"]},
            "vitals_and_key_results": {"vitals_last": {"bp": "120/80"}},
        },
        "errors": [],
        "missing_items": [],
        "inconsistencies": [],
        "recommended_corrections": [],
    }

    fixed = validator.fix_response(response)
    is_valid, error = validator.validate(fixed)

    assert is_valid, error
    assert "allergies" not in fixed["parsed_report"]
    assert fixed["parsed_report"]["unmapped_content"] == []
    assert fixed["parsed_report"]["content"]["allergies"] == {"allergies": ["NKDA"]}


def test_fix_response_normalizes_malformed_ai_missing_item_errors():
    validator = ResponseValidator()
    response = {
        "qa_method": "direct_qa",
        "overall_score": 90,
        "summary": "Test",
        "parsed_report": {
            "format": "text",
            "structure_used": "standard",
            "content": {
                "follow_up_and_instructions": {
                    "return_precautions": ["Return to ED if chest pain"],
                }
            },
            "unmapped_content": [],
        },
        "errors": [
            {
                "type": "missing_item",
                "section": "follow_up_and_instructions",
                "field": "return_precautions",
                "reason": "Required for high-risk cases",
            }
        ],
        "missing_items": [
            {
                "section": "follow_up_and_instructions",
                "field": "return_precautions",
            }
        ],
        "inconsistencies": [],
        "recommended_corrections": [],
    }

    fixed = validator.fix_response(response)

    assert fixed["errors"] == []
    assert fixed["missing_items"][0]["required_by"] == "quality_rule"
    assert fixed["missing_items"][0]["why_required"] == "Required for high-risk cases"
