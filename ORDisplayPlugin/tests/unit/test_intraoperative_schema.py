"""Schema coercion for LLM nulls."""

from app.models.window_schemas import NursingIntraoperativeFields


def test_intraoperative_accepts_null_notes_from_llm():
    payload = {
        "operationStaff": {"date": "2026-09-03"},
        "anesthesia": {"type": "GENERAL"},
        "position": {"position": "SUPINE", "note": None},
        "skinPreparationAndIncision": {},
        "foleyCatheter": {},
        "tourniquet": {},
        "diathermiaAndLaser": {"na": False, "note": None},
        "laser": {"na": True, "note": None},
        "drains": {"na": False, "entries": []},
        "specimens": {"na": False, "entries": []},
    }
    parsed = NursingIntraoperativeFields.model_validate(payload)
    assert parsed.position.note == ""
    assert parsed.diathermiaAndLaser.note == ""
    assert parsed.laser.note == ""


def test_intraoperative_coerces_numeric_electro_ranges():
    payload = {
        "diathermiaAndLaser": {
            "electroRangeCutting": 30,
            "electroRangeCoagulation": 25,
        },
    }
    parsed = NursingIntraoperativeFields.model_validate(payload)
    assert parsed.diathermiaAndLaser.electroRangeCutting == "30"
    assert parsed.diathermiaAndLaser.electroRangeCoagulation == "25"
