"""Tests for the eight window path specs."""

from app.core.window_registry import WINDOW_BY_ID, WINDOWS


def test_eight_windows_match_display_plugin_paths():
    assert len(WINDOWS) == 8
    assert WINDOW_BY_ID["nursing_time_out"].display_path == "/api/v1/windows/nursing/time-out"
    assert WINDOW_BY_ID["nursing_time_out"].role == "nurse"
    assert WINDOW_BY_ID["operative_note"].display_path == "/api/v1/windows/operative-note"
    assert WINDOW_BY_ID["anesthesia_observation_drugs"].role == "anesthetist"
