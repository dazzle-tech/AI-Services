"""Prompt contract for the three generation steps."""
from app.ai.prompts import (
    ROLE_PROFILES,
    build_highlight_prompt,
    build_summary_prompt,
    build_timeline_prompt,
)

EVENTS = [
    {
        "event_id": "evt-001",
        "date": "2026-03-13",
        "event_type": "lab",
        "title": "Troponin 0.8 ng/mL",
        "description": "Troponin 0.8 ng/mL, flagged high, on 2026-03-13.",
        "clinical_importance": "high",
        "source": "lab_results",
    }
]


def _blob(messages):
    return "\n".join(message["content"] for message in messages)


def test_timeline_prompt_carries_fidelity_rules_and_no_role():
    """The shared timeline step does not receive a viewer role."""
    blob = _blob(build_timeline_prompt({"patient_id": "pt-1", "vitals": []}))
    assert "STEP: timeline" in blob
    assert "PATIENT_DATA_JSON" in blob
    assert "VIEWER_ROLE" not in blob
    assert "mmHg" in blob
    assert "160/100" in blob
    assert "dose" in blob.lower()
    assert "single lab" in blob.lower() or "single value" in blob.lower()
    for role_name in ("nurse", "radiologist", "cardiologist"):
        assert role_name not in blob.lower()


def test_summary_prompt_uses_events_and_age_only():
    """The summary step is role-independent and problem-oriented."""
    blob = _blob(build_summary_prompt(EVENTS, age="58 years", gender="male"))
    assert "STEP: clinical_summary" in blob
    assert "TIMELINE_JSON" in blob
    assert "58 years" in blob
    assert "male" in blob
    assert "evt-001" in blob
    assert "0.8" in blob
    assert "problem-oriented" in blob
    assert "VIEWER_ROLE" not in blob
    assert "PATIENT_DATA_JSON" not in blob
    for role_name in ("nurse", "radiologist", "cardiologist"):
        assert role_name not in blob.lower()


def test_highlight_prompt_includes_the_requested_role_profile():
    """Highlights see the timeline and one role profile."""
    blob = _blob(build_highlight_prompt(EVENTS, "radiologist"))
    assert "STEP: role_highlights" in blob
    assert "VIEWER_ROLE: radiologist" in blob
    assert "penicillin" in blob.lower()
    assert "contrast" in blob.lower()
    assert "not documented" in blob.lower()
    assert "event_id" in blob
    assert "TIMELINE_JSON" in blob
    assert "PATIENT_DATA_JSON" not in blob
    assert "creatinine" in ROLE_PROFILES["radiologist"].lower()
    assert "insulin" in ROLE_PROFILES["nurse"].lower()
    assert "second troponin" in ROLE_PROFILES["cardiologist"].lower() or "one elevated troponin" in ROLE_PROFILES["cardiologist"].lower()


def test_model_name_is_not_hardcoded():
    """Application code reads the model from settings."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "app"
    source = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.py"))
    assert "gpt-4" not in source
    assert "gpt-3" not in source
    assert "ollama" not in source.lower()
    assert "llama" not in source.lower()
    assert "sk-" not in source
