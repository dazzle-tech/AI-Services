"""Voice in, clinical summary out."""

import base64
import io
import wave

from app.ai.prompts import SUMMARY_SYSTEM_PROMPT, build_user_prompt


def _make_silent_wav() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16000)
        wav_file.writeframes(b"\x00\x00" * 16000)
    return buffer.getvalue()


def test_prompt_is_for_one_speaker():
    assert "ONE person" in SUMMARY_SYSTEM_PROMPT
    assert "Do not turn the dictation into a conversation" in SUMMARY_SYSTEM_PROMPT
    user = build_user_prompt("No fever. Ibuprofen 400 mg.")
    assert "one speaker" in user
    assert "No fever. Ibuprofen 400 mg." in user


def test_summarize_returns_summary(client):
    response = client.post(
        "/api/v1/summarize",
        files={"audio": ("note.wav", _make_silent_wav(), "audio/wav")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "Assessment:" in body["summary"]
    assert "Plan:" in body["summary"]
    assert "transcript" in body


def test_summarize_json_base64(client):
    wav = _make_silent_wav()
    response = client.post(
        "/api/v1/summarize",
        json={"audio_base64": base64.b64encode(wav).decode("ascii"), "filename": "note.wav"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["summary"]


def test_missing_audio_400(client):
    response = client.post("/api/v1/summarize", data={"filename": "note.wav"})
    assert response.status_code == 400
    assert "audio" in response.json()["detail"]


def test_health(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["details"]["stub"] is True
