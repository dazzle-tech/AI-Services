"""Limits, readiness, dose support, polarity, and the Whisper gates."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.asr.whisper import keep_segment, low_confidence_numbers, pick_language
from app.core import metrics
from app.core.config import reload_settings
from app.live.checks import dose_is_supported, mentions, polarity_ok
from app.live.picked_up import enforce_picked_up, speakers_from_model
from app.models.schemas import Segment
from tests.test_live import LIVE_PATH, read_until, silence, start_message, tone

_GATES = SimpleNamespace(
    whisper_max_compression_ratio=2.4,
    whisper_no_speech_threshold=0.6,
    whisper_min_avg_logprob=-1.0,
)


def _seg(seg_id: str, text: str) -> Segment:
    return Segment(id=seg_id, speaker="patient", start_ms=0, end_ms=1, text=text, lang="en", final=True)


def test_start_timeout_closes_before_a_visit(client, monkeypatch):
    monkeypatch.setenv("START_TIMEOUT_SECONDS", "0.2")
    reload_settings()
    with client.websocket_connect(LIVE_PATH) as ws:
        message = ws.receive_json()
    assert message["type"] == "error"
    assert "start" in message["detail"].lower()


def test_idle_client_ends_with_warning_and_final(client, monkeypatch):
    monkeypatch.setenv("IDLE_TIMEOUT_SECONDS", "0.4")
    reload_settings()
    with client.websocket_connect(LIVE_PATH) as ws:
        ws.send_json(start_message())
        assert ws.receive_json()["type"] == "ready"
        messages = read_until(ws, "final")
    assert any(m["type"] == "warning" and "No audio" in m["detail"] for m in messages)
    assert messages[-1]["type"] == "final"


def test_oversized_frame_is_refused(client, monkeypatch):
    monkeypatch.setenv("MAX_FRAME_BYTES", "16")
    reload_settings()
    with client.websocket_connect(LIVE_PATH) as ws:
        ws.send_json(start_message())
        assert ws.receive_json()["type"] == "ready"
        ws.send_bytes(tone(0.1))
        message = ws.receive_json()
    assert message["type"] == "error"
    assert "too large" in message["detail"].lower()


def test_max_session_length_warns_and_sends_final(client, monkeypatch):
    monkeypatch.setenv("SESSION_WARN_SECONDS", "0.2")
    monkeypatch.setenv("MAX_SESSION_SECONDS", "0.5")
    reload_settings()
    with client.websocket_connect(LIVE_PATH) as ws:
        ws.send_json(start_message())
        assert ws.receive_json()["type"] == "ready"
        ws.send_bytes(tone(1.2))
        messages = read_until(ws, "final")
    warnings = [m for m in messages if m["type"] == "warning" and m["detail"] == "session_length"]
    assert warnings and warnings[0]["seconds"] >= 0.5
    assert messages[-1]["type"] == "final"
    assert messages[-1]["segments"]


def test_session_cap_rejects_the_second_visit_and_releases_the_slot(client, monkeypatch):
    monkeypatch.setenv("MAX_SESSIONS", "1")
    reload_settings()
    with client.websocket_connect(LIVE_PATH) as first:
        first.send_json(start_message())
        assert first.receive_json()["type"] == "ready"
        held = client.get("/api/v1/ready")
        assert held.status_code == 503
        assert held.json()["full"] is True
        assert held.json()["sessions_active"] == 1
        with client.websocket_connect(LIVE_PATH) as second:
            second.send_json(start_message())
            message = second.receive_json()
        assert message["type"] == "error"
        assert "busy" in message["detail"]
    ready = client.get("/api/v1/ready")
    assert ready.status_code == 200
    assert ready.json()["sessions_active"] == 0
    assert ready.json()["full"] is False
    assert "livescribe_sessions_active 0" in client.get("/api/v1/metrics").text


def test_hard_backlog_closes_the_socket(client, monkeypatch):
    monkeypatch.setenv("MAX_BACKLOG_HARD_SECONDS", "0.01")
    reload_settings()
    with client.websocket_connect(LIVE_PATH) as ws:
        ws.send_json(start_message())
        assert ws.receive_json()["type"] == "ready"
        ws.send_bytes(tone(0.5))
        message = ws.receive_json()
    assert message["type"] == "error"
    assert "busy" in message["detail"]


def test_ready_is_ok_when_a_slot_is_free(client):
    body = client.get("/api/v1/ready")
    assert body.status_code == 200
    payload = body.json()
    assert payload["ready"] is True
    assert payload["problems"] == []
    assert payload["full"] is False


def test_ready_is_503_when_speech_is_not_loaded(client):
    previous = client.app.state.transcriber
    client.app.state.transcriber = None
    try:
        body = client.get("/api/v1/ready")
    finally:
        client.app.state.transcriber = previous
    assert body.status_code == 503
    assert body.json()["ready"] is False
    assert any("speech" in problem for problem in body.json()["problems"])


def test_dev_pages_are_off_by_default(client):
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert client.get("/openapi.json").status_code == 404
    assert client.get("/try").status_code == 404
    root = client.get("/").json()
    assert root["ready"] == "/api/v1/ready"
    assert root["metrics"] == "/api/v1/metrics"
    assert "try" not in root
    assert "docs" not in root


@pytest.mark.parametrize(
    ("detail", "spoken", "supported"),
    [
        ("500 mg", "Take amoxicillin 500 mg once a day", True),
        ("500 mg daily", "Take amoxicillin 500 mg once a day", True),
        ("500 mg three times a day", "Take amoxicillin 500 mg once a day", False),
        ("5 g", "Take amoxicillin 500 mg once a day", False),
        ("50 mg", "Take amoxicillin 500 mg once a day", False),
        ("2 tablets", "two tablets in the morning", True),
        ("٥٠٠ ملغ", "خذ أموكسيسيلين ٥٠٠ ملغ مرة واحدة", True),
        ("500 mg twice daily", "٥٠٠ ملغ مرة واحدة", False),
        ("twice daily", "مرة واحدة", False),
    ],
)
def test_dose_is_supported_only_when_number_unit_and_frequency_were_said(detail, spoken, supported):
    assert dose_is_supported(detail, spoken) is supported


def test_latin_drug_names_are_whole_words_and_arabic_names_may_be_prefixed():
    assert mentions("the environment is noisy", "iron") is False
    assert mentions("she takes iron daily", "iron") is True
    assert mentions("خذ بالأسبرين اليوم", "أسبرين") is True


def test_a_changed_frequency_drops_the_detail_and_keeps_the_medicine():
    segments = [_seg("t1", "I take amoxicillin 500 mg once a day.")]
    raw = {"medications": [{"name": "amoxicillin", "detail": "500 mg three times a day", "segment_ids": ["t1"]}]}
    medication = enforce_picked_up(raw, segments, None).medications[0]
    assert medication.name == "amoxicillin"
    assert medication.detail is None
    assert medication.confirm is True


@pytest.mark.parametrize(
    ("item", "cited", "ok"),
    [
        ("Chest pain", ["Any chest pain?", "No."], False),
        ("Headache", ["No fever, but I have a headache."], True),
        ("Fever", ["No fever, but I have a headache."], False),
        ("صداع", ["ما عندي صداع"], False),
        ("No aura", ["No aura."], True),
    ],
)
def test_polarity_follows_the_clause_that_names_the_item(item, cited, ok):
    assert polarity_ok(item, cited) is ok


def test_a_denied_symptom_is_dropped_from_the_list():
    segments = [_seg("t1", "Any chest pain?"), _seg("t2", "No.")]
    raw = {"symptoms": [{"text": "Chest pain", "segment_ids": ["t1", "t2"]}]}
    assert enforce_picked_up(raw, segments, None).symptoms == []


def test_whisper_gates_drop_a_hallucination_and_keep_a_clear_quiet_piece():
    hallucination = SimpleNamespace(compression_ratio=3.1, no_speech_prob=0.1, avg_logprob=-0.2)
    quiet_and_poor = SimpleNamespace(compression_ratio=1.2, no_speech_prob=0.9, avg_logprob=-1.4)
    quiet_but_clear = SimpleNamespace(compression_ratio=1.1, no_speech_prob=0.95, avg_logprob=-0.3)
    missing = SimpleNamespace()
    assert keep_segment(hallucination, _GATES) is False
    assert keep_segment(quiet_and_poor, _GATES) is False
    assert keep_segment(quiet_but_clear, _GATES) is True
    assert keep_segment(missing, _GATES) is True


def test_an_unsure_number_is_flagged_and_persian_is_mapped_to_arabic():
    segment = SimpleNamespace(
        words=[
            SimpleNamespace(word=" 128,", probability=0.4),
            SimpleNamespace(word="normal", probability=0.2),
            SimpleNamespace(word="76", probability=0.9),
        ]
    )
    assert low_confidence_numbers(segment, 0.6) == ["128"]
    info = SimpleNamespace(language="fa", all_language_probs=[("fa", 0.8), ("ar", 0.15), ("en", 0.04)])
    assert pick_language(info, ["ar", "en"]) == "ar"
    assert pick_language(SimpleNamespace(language="en", all_language_probs=[]), ["ar", "en"]) is None


def test_a_model_unknown_speaker_is_ignored():
    segments = [_seg("t1", "About three tablets a day.")]
    assert speakers_from_model({"speakers": {"t1": "unknown"}}, segments) == {}


def test_partials_skipped_counter_moves_when_the_backlog_is_soft(client, monkeypatch):
    monkeypatch.setenv("MAX_BACKLOG_SECONDS", "0")
    monkeypatch.setenv("MAX_BACKLOG_HARD_SECONDS", "1000")
    reload_settings()
    before = metrics.partials_skipped_total.value
    with client.websocket_connect(LIVE_PATH) as ws:
        ws.send_json(start_message())
        assert ws.receive_json()["type"] == "ready"
        ws.send_bytes(tone(5.0))
        ws.send_bytes(silence(1.0))
        ws.send_json({"type": "stop"})
        read_until(ws, "final")
    assert metrics.partials_skipped_total.value > before
