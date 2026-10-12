"""Normalize ORScribe analyze / case JSON into a flat mapping payload."""

from __future__ import annotations

from typing import Any


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def normalize_orscribe_output(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Accept ORScribe AnalyzeAudioResponse or CaseResponse (or a mix) and
    expose stable source_paths for ViewDecoders.

    AnalyzeAudioResponse:
      timeline.{events, medications_administered, instrument_counts}
      checklist.{sign_in, time_out, sign_out}

    CaseResponse:
      timeline, medications, instrument_counts, checklist_result
    """
    timeline = _as_dict(raw.get("timeline"))
    checklist = _as_dict(raw.get("checklist") or raw.get("checklist_result"))
    sign_in = _as_dict(checklist.get("sign_in"))
    time_out = _as_dict(checklist.get("time_out"))
    sign_out = _as_dict(checklist.get("sign_out"))

    events = _as_list(timeline.get("events") or raw.get("events"))
    medications = _as_list(
        timeline.get("medications_administered")
        or raw.get("medications_administered")
        or raw.get("medications")
    )
    counts = _as_list(
        timeline.get("instrument_counts") or raw.get("instrument_counts")
    )

    flat = dict(raw)
    flat["events"] = events
    flat["medications_administered"] = medications
    flat["instrument_counts"] = counts
    flat["checklist"] = checklist
    flat["sign_in"] = sign_in
    flat["time_out"] = time_out
    flat["sign_out"] = sign_out
    if "needs_review" not in flat:
        flat["needs_review"] = False
    return flat
