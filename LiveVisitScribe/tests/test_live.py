from __future__ import annotations

import asyncio

import numpy as np

from app.asr.stub import DEFAULT_SCRIPT, StubTranscriber
from app.core.config import settings
from app.live import picked_up
from app.live.picked_up import enforce_picked_up, speakers_from_model
from app.live.session import LiveSession
from app.live.speaker import guess_speaker
from app.live.text_utils import detect_lang
from app.models.schemas import PatientContext, Segment

LIVE_PATH = "/api/v1/live"
RATE = 16000


def tone(seconds: float) -> bytes:
    """Loud audio (counts as speech). The stub transcriber ignores the samples themselves."""
    t = np.arange(int(RATE * seconds)) / RATE
    return (0.3 * np.sin(2 * np.pi * 440 * t) * 32767).astype("<i2").tobytes()


def silence(seconds: float) -> bytes:
    return b"\x00\x00" * int(RATE * seconds)


def start_message(**extra) -> dict:
    return {"type": "start", "sample_rate": RATE, "channels": 1, **extra}


def read_until(ws, *stop_types: str) -> list[dict]:
    messages = []
    while True:
        message = ws.receive_json()
        messages.append(message)
        if message["type"] in stop_types:
            return messages


def run_visit(client, turns: int, **start_extra) -> list[dict]:
    """Send `turns` spoken lines (each followed by silence), then stop. Returns everything up to `final`."""
    with client.websocket_connect(LIVE_PATH) as ws:
        ws.send_json(start_message(**start_extra))
        assert ws.receive_json()["type"] == "ready"
        for _ in range(turns):
            ws.send_bytes(tone(1.2))
            ws.send_bytes(silence(1.0))
        ws.send_json({"type": "stop"})
        return read_until(ws, "final")


def finals(messages: list[dict]) -> list[dict]:
    return [m for m in messages if m["type"] == "segment" and m["final"]]


def last_picked_up(messages: list[dict]) -> dict:
    return [m for m in messages if m["type"] == "picked_up"][-1]


# --- the socket ----------------------------------------------------------


def test_start_pcm_stop_returns_ready_final_segment_and_final(client):
    with client.websocket_connect(LIVE_PATH) as ws:
        ws.send_json(start_message())
        assert ws.receive_json() == {"type": "ready", "sample_rate": RATE, "channels": 1}
        ws.send_bytes(tone(1.2))
        ws.send_bytes(silence(1.0))
        ws.send_bytes(tone(1.2))  # still being spoken when Stop is pressed
        ws.send_json({"type": "stop"})
        messages = read_until(ws, "final")

    segments = finals(messages)
    assert segments[0]["id"] == "t1" and segments[0]["final"] is True
    assert segments[0]["text"] == DEFAULT_SCRIPT[0]
    assert segments[0]["speaker"] == "doctor" and segments[0]["lang"] == "en"
    assert 0 <= segments[0]["start_ms"] < segments[0]["end_ms"]
    assert [s["id"] for s in segments] == ["t1", "t2"]

    final = messages[-1]
    assert final["type"] == "final"
    assert [s["id"] for s in final["segments"]] == ["t1", "t2"]
    assert abs(final["audio_ms"] - 3400) <= 40


def test_audio_before_start_returns_error(client):
    with client.websocket_connect(LIVE_PATH) as ws:
        ws.send_bytes(tone(0.5))
        message = ws.receive_json()
    assert message["type"] == "error"
    assert "start" in message["detail"].lower()


def test_invalid_start_and_unknown_control_return_errors(client):
    with client.websocket_connect(LIVE_PATH) as ws:
        ws.send_json({"type": "start", "sample_rate": 100})
        assert ws.receive_json()["type"] == "error"
        ws.send_json({"type": "pause"})
        assert ws.receive_json()["type"] == "error"
        ws.send_json({"type": "dance"})
        assert ws.receive_json()["type"] == "error"
        ws.send_text("not json")
        assert ws.receive_json()["type"] == "error"


def test_long_line_gets_a_partial_then_a_final_with_the_same_id(client):
    with client.websocket_connect(LIVE_PATH) as ws:
        ws.send_json(start_message())
        ws.receive_json()
        ws.send_bytes(tone(5.0))  # past STREAM_CHUNK_SECONDS (4 s) while still talking
        ws.send_bytes(silence(1.0))
        ws.send_json({"type": "stop"})
        messages = read_until(ws, "final")

    segments = [m for m in messages if m["type"] == "segment"]
    assert [(s["id"], s["final"]) for s in segments] == [("t1", False), ("t1", True)]
    assert len(segments[0]["text"]) < len(segments[1]["text"])
    assert segments[1]["text"] == DEFAULT_SCRIPT[0]


def test_pause_sends_no_new_segments_until_resume(client):
    with client.websocket_connect(LIVE_PATH) as ws:
        ws.send_json(start_message())
        ws.receive_json()
        ws.send_bytes(tone(1.2))
        ws.send_bytes(silence(1.0))
        ws.send_json({"type": "pause"})
        before = read_until(ws, "paused")
        assert [m["id"] for m in finals(before)] == ["t1"]

        ws.send_bytes(tone(1.2))
        ws.send_bytes(silence(1.0))
        ws.send_json({"type": "resume"})
        while_paused = read_until(ws, "resumed")
        assert not [m for m in while_paused if m["type"] == "segment"]

        ws.send_bytes(tone(1.2))
        ws.send_bytes(silence(1.0))
        ws.send_json({"type": "stop"})
        after = read_until(ws, "final")

    second = finals(after)
    assert [s["id"] for s in second] == ["t2"]
    assert second[0]["text"] == DEFAULT_SCRIPT[1]  # the audio sent while paused was not transcribed
    assert after[-1]["audio_ms"] < 2 * 2300 + 100  # and does not count toward the timeline


def test_health_reports_stub_mode(client):
    body = client.get("/api/v1/health").json()
    assert body == {"status": "ok", "asr": "stub", "picked_up": "stub"}


# --- picked up so far ----------------------------------------------------


def test_stub_visit_picks_up_complaint_symptoms_exam_and_flags_the_dose(client):
    messages = run_visit(client, turns=7)
    picked = last_picked_up(messages)

    assert picked["complaint"] == {"text": "I have had a daily headache for two weeks", "segment_ids": ["t2"]}
    assert [s["text"] for s in picked["symptoms"]] == ["Mild nausea in the mornings", "No aura"]
    assert [e["text"] for e in picked["exam"]] == ["Blood pressure is 128 over 82", "Neuro exam is normal"]
    assert picked["medications"] == [
        {"name": "Neurofen", "detail": "About three tablets a day", "confirm": True, "segment_ids": ["t5", "t6"]}
    ]
    assert messages[-1]["type"] == "final" and len(messages[-1]["segments"]) == 7


def test_picked_up_medication_whose_segment_id_does_not_exist_is_removed(client, monkeypatch):
    async def fake(segments, context):
        return {
            "symptoms": [{"text": "daily headache", "segment_ids": ["t2"]}],
            "medications": [{"name": "Ghostdrug", "detail": "5 mg", "segment_ids": ["t99"]}],
        }

    monkeypatch.setattr(picked_up, "raw_extract", fake)
    picked_messages = [m for m in run_visit(client, turns=2) if m["type"] == "picked_up"]

    assert picked_messages
    assert all(m["medications"] == [] for m in picked_messages)
    assert [s["text"] for s in picked_messages[-1]["symptoms"]] == ["daily headache"]


def test_picked_up_item_that_only_restates_patient_context_is_removed(client, monkeypatch):
    async def fake(segments, context):
        return {
            "symptoms": [
                {"text": "Other migraine", "segment_ids": ["t2"]},
                {"text": "G43.8 Other migraine", "segment_ids": ["t2"]},
                {"text": "daily headache", "segment_ids": ["t2"]},
            ],
            "medications": [{"name": "Lisinopril 10 mg", "detail": None, "segment_ids": ["t2"]}],
            "exam": [{"text": "Allergic to silk", "segment_ids": ["t2"]}],
        }

    monkeypatch.setattr(picked_up, "raw_extract", fake)
    context = {
        "chronic_diseases": [],
        "active_medications": ["Lisinopril 10 mg"],
        "allergies": ["silk", "wool", "soya"],
        "known_diagnoses": ["G43.8 Other migraine"],
    }
    picked = last_picked_up(run_visit(client, turns=2, patient_context=context))

    assert [s["text"] for s in picked["symptoms"]] == ["daily headache"]
    assert picked["medications"] == []
    assert picked["exam"] == []


# --- the checks themselves -----------------------------------------------


def _seg(seg_id: str, text: str) -> Segment:
    return Segment(id=seg_id, speaker="patient", start_ms=0, end_ms=1, text=text, lang="en", final=True)


def test_item_cited_only_by_a_question_is_dropped():
    segments = [_seg("t1", "Any nausea or vision changes?"), _seg("t2", "No nausea.")]
    raw = {
        "symptoms": [
            {"text": "No vision changes", "segment_ids": ["t1"]},
            {"text": "No nausea", "segment_ids": ["t1", "t2"]},
        ]
    }
    result = enforce_picked_up(raw, segments, None)
    assert [s.text for s in result.symptoms] == ["No nausea"]


def test_invented_dose_is_removed_but_a_spoken_medicine_stays():
    segments = [_seg("t1", "I take Neurofen about three tablets a day.")]
    raw = {"medications": [{"name": "Neurofen", "detail": "400 mg", "segment_ids": ["t1"]}]}
    medication = enforce_picked_up(raw, segments, None).medications[0]
    assert medication.name == "Neurofen" and medication.detail is None and medication.confirm is True


def test_medicine_from_the_chart_but_not_said_is_dropped_and_said_one_is_kept():
    context = PatientContext(active_medications=["Lisinopril 10 mg"])
    segments = [_seg("t1", "I have a headache."), _seg("t2", "I take Lisinopril 10 mg every morning.")]
    raw = {
        "medications": [
            {"name": "Lisinopril 10 mg", "detail": None, "segment_ids": ["t1"]},
            {"name": "Lisinopril 10 mg", "detail": "every morning", "segment_ids": ["t2"]},
        ]
    }
    result = enforce_picked_up(raw, segments, context)
    assert [(m.name, m.segment_ids) for m in result.medications] == [("Lisinopril 10 mg", ["t2"])]


def test_partials_are_skipped_when_behind_but_the_final_line_still_comes():
    sent: list[dict] = []

    async def emit(message: dict) -> None:
        sent.append(message)

    async def run() -> None:
        session = LiveSession(transcriber=StubTranscriber(), emit=emit, settings=settings)
        await session.feed(tone(5.0), allow_partial=False)
        await session.feed(silence(1.0), allow_partial=False)
        await session.stop()

    asyncio.run(run())
    segments = [m for m in sent if m["type"] == "segment"]
    assert [(s["id"], s["final"]) for s in segments] == [("t1", True)]


def test_speaker_and_language_guesses():
    assert guess_speaker("Any nausea, or visual aura before the pain?") == "doctor"
    assert guess_speaker("I have had a daily headache for two weeks.") == "patient"
    assert guess_speaker("About three tablets a day.") == "patient"
    assert guess_speaker("Alright, Doctor, is my blood pressure okay today?") == "patient"
    assert guess_speaker("When shall I come back if the headache does not improve?") == "patient"
    assert detect_lang("كم حبة Neurofen تاخذين باليوم؟") == "mixed"
    assert detect_lang("صداع منذ يومين") == "ar"
    assert detect_lang("Blood pressure is 128 over 82") == "en"


def test_speaker_labels_keep_only_known_roles():
    segments = [_seg("t1", "What should I do at home?"), _seg("t2", "Try to drink fluids regularly.")]
    labels = speakers_from_model(
        {
            "speakers": {
                "t1": "Patient",
                "t9": "doctor",
                "t2": "clinician",
            }
        },
        segments,
    )
    listed = speakers_from_model(
        {"speakers": [{"id": "t2", "speaker": "doctor"}, {"id": "t1", "speaker": "nope"}]},
        segments,
    )
    assert labels == {"t1": "patient"}
    assert listed == {"t2": "doctor"}


def test_model_speaker_labels_replace_the_word_guess(client, monkeypatch):
    async def fake(segments, context):
        return {"speakers": {"t1": "patient", "t2": "doctor"}, "symptoms": []}

    monkeypatch.setattr(picked_up, "raw_extract", fake)
    messages = run_visit(client, turns=2)
    final = messages[-1]

    assert [(segment["id"], segment["speaker"]) for segment in final["segments"]] == [
        ("t1", "patient"),
        ("t2", "doctor"),
    ]
    assert any(
        message["type"] == "segment" and message["id"] == "t1" and message["speaker"] == "patient"
        for message in messages
    )


# --- Asklepios record ------------------------------------------------------


def test_stub_visit_builds_record_payloads_with_evidence_and_missing_required(client):
    picked = last_picked_up(run_visit(client, turns=7))
    record = picked["record"]

    vital = record["vital_sign"]
    assert vital["patientId"] is None and vital["encounterId"] is None
    assert (vital["bloodPressureSystolic"], vital["bloodPressureDiastolic"]) == (128, 82)
    assert vital["heartRate"] is None and vital["isActive"] is True and vital["isTriage"] is False
    assert picked["record_status"]["vital_sign"] == "partial"
    assert picked["missing_required"]["vital_sign"] == [
        "heartRate", "temperature", "oxygenSaturation", "respiratoryRate",
    ]
    assert picked["record_evidence"]["vital_sign.bloodPressureSystolic"] == ["t7"]

    assert record["body_measurements"] is None and picked["record_status"]["body_measurements"] == "empty"
    assert record["clinical_visit"]["chiefComplaint"] == "I have had a daily headache for two weeks"
    assert record["clinical_visit"]["historyOfPresentIllness"] == "Mild nausea in the mornings. No aura."
    assert record["nursing_assessment"]["reasonOfVisit"] == "I have had a daily headache for two weeks"
    assert record["nursing_assessment"]["byPatient"] is True
    assert "patient_diagnosis" not in record  # diagnoses come from ConvoVoiceAgent on stop


def test_record_fields_must_be_said_plausible_and_not_questions():
    segments = [
        _seg("t1", "Is your pulse around 70?"),
        _seg("t2", "Pulse is 78. Temperature is 36.8."),
        _seg("t3", "Weight is 70 kg."),
        _seg("t4", "Blood pressure is 80 over 120."),
    ]

    def cite(value, *ids):
        return {"value": value, "segment_ids": list(ids)}

    raw = {
        "record": {
            "vital_sign": {
                "heartRate": cite(70, "t1"),  # only a question
                "temperature": cite(37.5, "t2"),  # 37.5 was not said
                "respiratoryRate": cite(16, "t99"),  # no such segment
                "bloodPressureSystolic": cite(80, "t4"),  # swapped pair, asked again
                "bloodPressureDiastolic": cite(120, "t4"),
                "edema": cite("NONE", "t2"),  # allowed value, but the cited line never mentions swelling
            },
            "body_measurements": {"weight": cite(70, "t3")},
        }
    }
    result = enforce_picked_up(raw, segments, None)
    vital = result.record["vital_sign"]
    assert vital["heartRate"] == 78 and vital["temperature"] == 36.8  # said aloud; the model's other numbers were not
    assert vital["bloodPressureSystolic"] is None and vital["bloodPressureDiastolic"] is None
    assert vital["respiratoryRate"] is None
    assert result.record_status["vital_sign"] == "partial"
    assert result.record["body_measurements"]["weight"] == 70
    assert result.missing_required["body_measurements"] == ["height"]


def test_picked_up_record_fills_the_same_spoken_fields_as_the_draft():
    segments = [
        _seg("t1", "Head circumference 55 centimeters. Weight is 71.4 kg."),
        _seg("t2", "The pain is mostly a dull ache, about a 2 when I am resting."),
        _seg("t3", "Pain score 2 out of 10."),
    ]
    result = enforce_picked_up({"record": {}}, segments, None)
    assert result.record["body_measurements"]["headCircumference"] == 55
    assert result.record["body_measurements"]["weight"] == 71.4
    pain = result.record["pain_assessment"]
    assert pain["painDescription"] == "dull ache"
    assert pain["painPattern"] is None and pain["painDegree"] is None
    assert pain["painLevel"] == "LEVEL_2" and pain["painAssessmentType"] == "NUMERIC"
    assert result.record_evidence["body_measurements.headCircumference"] == ["t1"]
    assert result.record_evidence["pain_assessment.painDescription"] == ["t2"]
    assert result.missing_required["pain_assessment"] == ["painDegree"]
