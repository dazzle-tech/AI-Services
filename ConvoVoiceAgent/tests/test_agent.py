"""ConvoVoiceAgent forwards audio to ConvoScribe, then the note to SystemDisplayPlugin."""

import base64
import io
import json
import wave

import httpx
import pytest
import respx

from app.core.config import settings

ANALYZE_PATH = "/api/v1/analyze"


def _make_silent_wav(duration_seconds: float = 1.0, sample_rate: int = 16000) -> bytes:
    num_frames = int(duration_seconds * sample_rate)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"\x00\x00" * num_frames)
    return buffer.getvalue()


def _analyze_json():
    return {
        "raw_transcript": {"segments": []},
        "role_map": {"SPEAKER_00": "doctor", "SPEAKER_01": "patient"},
        "role_confidence": "high",
        "role_reasoning": "Clear roles",
        "needs_review": False,
        "summary": {
            "subjective": "Headache for 3 days.",
            "objective": "Alert, afebrile.",
            "assessment": "Tension headache.",
            "plan": "Ibuprofen as needed.",
            "medications_mentioned": ["ibuprofen"],
            "follow_up": "Two weeks.",
            "flags": [],
        },
        "narrative_summary": None,
        "clinical_document": None,
    }


def _display_json():
    return {
        "results": [
            {
                "view_id": "soap_note",
                "data": {"ChiefComplaint": "Headache", "Assessments": "Tension headache."},
                "warnings": [],
            }
        ]
    }


@respx.mock
def test_analyze_returns_display_results(client):
    analyze_url = f"{settings.convoscribe_base_url}/api/v1/analyze"
    reshape_url = f"{settings.system_display_base_url}/api/v1/reshape"
    respx.post(analyze_url).mock(return_value=httpx.Response(200, json=_analyze_json()))
    reshape = respx.post(reshape_url).mock(return_value=httpx.Response(200, json=_display_json()))

    files = {"audio": ("visit.wav", _make_silent_wav(), "audio/wav")}
    response = client.post(ANALYZE_PATH, files=files)

    assert response.status_code == 200, response.text
    assert response.json() == _display_json()
    sent = json.loads(reshape.calls.last.request.content)
    assert sent["stage1_output"]["subjective"] == "Headache for 3 days."
    assert sent["stage1_output"]["plan"] == "Ibuprofen as needed."
    assert sent["view_ids"] == ["soap_note"]
    assert sent["context"] == "appointment"
    assert sent["purpose"] == "soap_note"


@respx.mock
def test_analyze_json_base64(client):
    analyze_url = f"{settings.convoscribe_base_url}/api/v1/analyze"
    reshape_url = f"{settings.system_display_base_url}/api/v1/reshape"
    respx.post(analyze_url).mock(return_value=httpx.Response(200, json=_analyze_json()))
    respx.post(reshape_url).mock(return_value=httpx.Response(200, json=_display_json()))

    wav = _make_silent_wav()
    response = client.post(
        ANALYZE_PATH,
        json={
            "audio_base64": base64.b64encode(wav).decode("ascii"),
            "filename": "visit.wav",
            "view_ids": ["soap_note", "vital_signs"],
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["results"][0]["view_id"] == "soap_note"


@respx.mock
def test_custom_view_ids_are_forwarded(client):
    analyze_url = f"{settings.convoscribe_base_url}/api/v1/analyze"
    reshape_url = f"{settings.system_display_base_url}/api/v1/reshape"
    respx.post(analyze_url).mock(return_value=httpx.Response(200, json=_analyze_json()))
    reshape = respx.post(reshape_url).mock(return_value=httpx.Response(200, json=_display_json()))

    response = client.post(
        ANALYZE_PATH,
        files={"audio": ("visit.wav", _make_silent_wav(), "audio/wav")},
        data={
            "view_ids": "soap_note, vital_signs",
            "context_type": "ward_round",
            "purpose": "soap_note",
        },
    )
    assert response.status_code == 200, response.text
    sent = json.loads(reshape.calls.last.request.content)
    assert sent["view_ids"] == ["soap_note", "vital_signs"]
    assert sent["context"] == "ward_round"


def test_missing_audio_400(client):
    response = client.post(ANALYZE_PATH, data={"purpose": "soap_note"})
    assert response.status_code == 400
    assert "audio" in response.json()["detail"]


@respx.mock
def test_convoscribe_failure_502(client):
    analyze_url = f"{settings.convoscribe_base_url}/api/v1/analyze"
    respx.post(analyze_url).mock(return_value=httpx.Response(500, text="analyze boom"))

    files = {"audio": ("visit.wav", _make_silent_wav(), "audio/wav")}
    response = client.post(ANALYZE_PATH, files=files)
    assert response.status_code == 502
    assert "ConvoScribe analyze failed" in response.json()["detail"]


@respx.mock
def test_display_failure_502(client):
    analyze_url = f"{settings.convoscribe_base_url}/api/v1/analyze"
    reshape_url = f"{settings.system_display_base_url}/api/v1/reshape"
    respx.post(analyze_url).mock(return_value=httpx.Response(200, json=_analyze_json()))
    respx.post(reshape_url).mock(return_value=httpx.Response(422, text="no view succeeded"))

    files = {"audio": ("visit.wav", _make_silent_wav(), "audio/wav")}
    response = client.post(ANALYZE_PATH, files=files)
    assert response.status_code == 502
    assert "SystemDisplayPlugin reshape failed" in response.json()["detail"]


@respx.mock
def test_health_pings_downstream(client):
    respx.get(f"{settings.convoscribe_base_url}/openapi.json").mock(
        return_value=httpx.Response(200, json={"status": "ok"})
    )
    respx.get(f"{settings.system_display_base_url}/api/v1/health").mock(
        return_value=httpx.Response(200, json={"status": "ok"})
    )
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["downstream"]["convoscribe"] == "ok"
    assert body["downstream"]["system_display_plugin"] == "ok"


def test_narrative_summary_becomes_subjective():
    from app.services.agent_service import stage1_output_from_analyze

    stage1 = stage1_output_from_analyze(
        {
            "summary": None,
            "narrative_summary": {"summary": "Visit about a cough.", "follow_up": "Return if worse."},
            "clinical_document": None,
        }
    )
    assert stage1["subjective"] == "Visit about a cough."
    assert stage1["plan"] == "Return if worse."
