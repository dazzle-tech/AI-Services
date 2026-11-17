"""Unit tests for the date normalizer that runs before the AI steps."""
from datetime import date
from unittest.mock import MagicMock

from app.services.date_normalizer import (
    find_document_date,
    infer_date_order,
    normalize_dates,
    parse_birth_date,
)
from app.services.relevance_service import RelevanceService

BIRTH = date(2004, 3, 2)

LAB_TEXT = (
    "D.O.B / AGE\n02/03/2004 (22 Years 8 Months 14\nDays)\n"
    "AST (Aspartate Aminotransferase)\n52.00 U/L\n10.0 - 40.0\n16/11/2026 09:30 AM\n"
)


class TestOrderFromNumbers:
    def test_value_above_twelve_in_first_slot_is_day_first(self):
        assert infer_date_order("Result 16/11/2026", None) == ("dmy", "numbers")

    def test_value_above_twelve_in_second_slot_is_month_first(self):
        assert infer_date_order("Result 11/16/2026", None) == ("mdy", "numbers")

    def test_numbers_decide_before_the_birth_date_is_consulted(self):
        assert infer_date_order(LAB_TEXT, BIRTH) == ("dmy", "numbers")


class TestOrderFromBirthDate:
    def test_ambiguous_dates_follow_the_birth_date_day_first(self):
        text = "DOB: 02/03/2004\nResult date: 05/06/2026"
        assert infer_date_order(text, BIRTH) == ("dmy", "birth_date")

    def test_ambiguous_dates_follow_the_birth_date_month_first(self):
        text = "DOB: 03/02/2004\nResult date: 05/06/2026"
        assert infer_date_order(text, BIRTH) == ("mdy", "birth_date")

    def test_default_is_day_first_when_nothing_decides(self):
        assert infer_date_order("Result date: 05/06/2026", BIRTH) == ("dmy", "default")
        assert infer_date_order("Result date: 05/06/2026", None) == ("dmy", "default")


class TestNormalizeDates:
    def test_unambiguous_day_first_dates_become_iso(self):
        result = normalize_dates(LAB_TEXT, BIRTH)
        assert "2004-03-02" in result.text
        assert "2026-11-16 09:30 AM" in result.text
        assert "10.0 - 40.0" in result.text  # reference ranges stay untouched
        assert result.converted == 2

    def test_ambiguous_dates_use_the_order_learned_from_the_birth_date(self):
        mdy = normalize_dates("DOB: 03/02/2004\nResult date: 05/06/2026", BIRTH)
        dmy = normalize_dates("DOB: 02/03/2004\nResult date: 05/06/2026", BIRTH)
        assert "2004-03-02" in mdy.text and "2026-05-06" in mdy.text
        assert "2004-03-02" in dmy.text and "2026-06-05" in dmy.text

    def test_a_self_deciding_date_keeps_its_own_order_in_a_mixed_document(self):
        result = normalize_dates("A 16/11/2026 and B 11/16/2026", BIRTH)
        assert result.text == "A 2026-11-16 and B 2026-11-16"

    def test_dot_and_hyphen_separators(self):
        assert normalize_dates("Date 16.11.2026 / 17-11-2026", None).text == "Date 2026-11-16 / 2026-11-17"

    def test_iso_dates_and_impossible_dates_are_left_alone(self):
        text = "Done 2026-11-16, odd 31/02/2026, ratio 1.5-2.5"
        assert normalize_dates(text, None).text == text

    def test_empty_text(self):
        assert normalize_dates("", None).text == ""


class TestFindDocumentDate:
    def test_skips_the_birth_line_and_birth_date(self):
        text = normalize_dates(LAB_TEXT, BIRTH).text
        assert find_document_date(text, BIRTH, today=date(2026, 11, 17)) == date(2026, 11, 16)

    def test_prefers_the_latest_past_date(self):
        text = "Collected 2026-01-05\nResult 2026-01-07\nNext visit 2027-01-01"
        assert find_document_date(text, None, today=date(2026, 11, 17)) == date(2026, 1, 7)

    def test_none_when_only_birth_info(self):
        assert find_document_date("Date of Birth: 1980-05-14", None) is None


def test_parse_birth_date():
    assert parse_birth_date("2004-03-02") == BIRTH
    assert parse_birth_date(None) is None
    assert parse_birth_date("not a date") is None


class TestRelevanceUsesTheNormalizedText:
    def test_model_without_a_date_cannot_make_a_recent_document_irrelevant(self):
        ai = MagicMock()
        ai.classify_relevance.return_value = {
            "document_date": None,
            "is_relevant": False,
            "reason": "radiology_report document dated 2026-11-16 exceeds the relevance window of 365 days.",
        }
        text = normalize_dates(LAB_TEXT, BIRTH).text
        # A fixed "today" is not injectable, so use dates relative to the real one.
        today = date.today()
        text = text.replace("2026-11-16", today.isoformat())

        outcome = RelevanceService(ai).check(text, [], "radiology_report", BIRTH)

        assert outcome.is_relevant is True
        assert outcome.reason is None
        assert outcome.document_date == today.isoformat()


import pytest as _pytest

from app.models.schemas import LabResultEntry, PrescriptionData
from app.services.date_normalizer import format_output_date as _format_output_date


@_pytest.mark.parametrize(
    "raw, expected",
    [
        ("2026-11-10", "2026-11-10"),
        ("2026-11-10T19:10:00Z", "2026-11-10"),
        ("10/11/2026 07:10 PM", "2026-11-10"),
        ("12/24/2026", "2026-12-24"),
        ("5/6/2026", "2026-06-05"),
        ("10 November 2026", "2026-11-10"),
        ("10th Nov, 2026", "2026-11-10"),
        ("November 10, 2026 7:10 PM", "2026-11-10"),
        ("Tuesday, 3 March 2026", "2026-03-03"),
        ("10.11.2026", "2026-11-10"),
        ("unknown", "unknown"),
        ("", None),
        (None, None),
    ],
)
def test_format_output_date_is_iso(raw, expected):
    assert _format_output_date(raw) == expected


def test_structured_dates_are_returned_as_iso():
    assert LabResultEntry(testName="AST", resultDate="10/11/2026 07:10 PM").result_date == "2026-11-10"
    assert PrescriptionData(prescription_date="March 3, 2026").prescription_date == "2026-03-03"
