"""Ambient draft with USE_LLM_STUB=true, a fake ConvoScribe, and a fake SystemDisplayPlugin."""

import base64
import io
import json
import wave

import httpx
import pytest
import respx
from fastapi import HTTPException

from app.ai import ambient_stub
from app.core.config import reload_settings, settings
from app.services.ambient_draft import SOAP_NOTE_FIELDS

DRAFT_PATH = "/api/v1/draft"
REGENERATE_PATH = "/api/v1/sections/regenerate"


@pytest.fixture(autouse=True)
def llm_stub(test_env, monkeypatch):
    monkeypatch.setenv("USE_LLM_STUB", "true")
    monkeypatch.setenv("AMBIENT_LOW_CONFIDENCE_THRESHOLD", "0.6")
    reload_settings()


def _wav() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16000)
        wav_file.writeframes(b"\x00\x00" * 16000)
    return buffer.getvalue()


def _segment(label, start, end, text, confidence):
    return {"speaker_label": label, "start_time": start, "end_time": end, "text": text, "confidence": confidence}


def _convoscribe_json():
    return {
        "raw_transcript": {
            "segments": [
                _segment("SPEAKER_00", 0.0, 2.0, "Good morning, what brings you in today?", 0.95),
                _segment("SPEAKER_01", 2.0, 6.0, "I have had a sore throat and fever for three days.", 0.93),
                _segment("SPEAKER_01", 6.0, 9.0, "No cough. I am allergic to penicillin.", 0.9),
                _segment("SPEAKER_00", 9.0, 13.0, "On examination the throat is red and the tonsils are swollen.", 0.92),
                _segment("SPEAKER_00", 13.0, 16.0, "This looks like tonsillitis, possibly viral.", 0.9),
                _segment("SPEAKER_00", 16.0, 20.0, "Take azithromycin 500 mg once daily for three days.", 0.35),
                _segment("SPEAKER_00", 20.0, 24.0, "Follow up in 1 week, and go to the emergency if it gets worse.", 0.9),
                _segment("SPEAKER_01", 24.0, 27.0, "شكرا دكتور, the pain is worse at night.", 0.88),
            ]
        },
        "role_map": {"SPEAKER_00": "doctor", "SPEAKER_01": "patient"},
        "role_confidence": "high",
        "role_reasoning": "Clear roles",
        "needs_review": False,
        "summary": {"subjective": "", "objective": "", "assessment": "", "plan": "", "follow_up": ""},
    }


def _fake_reshape(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    results = [
        {
            "view_id": view["view_id"],
            "data": {f["field_name"]: body["stage1_output"].get(f["source_path"]) for f in view["fields"]},
            "warnings": [],
        }
        for view in body.get("views", [])
    ]
    return httpx.Response(200, json={"results": results})


@pytest.fixture
def downstream():
    with respx.mock(assert_all_called=False) as mock:
        analyze = mock.post(f"{settings.convoscribe_base_url}/api/v1/analyze").mock(
            return_value=httpx.Response(200, json=_convoscribe_json())
        )
        reshape = mock.post(f"{settings.system_display_base_url}/api/v1/reshape").mock(side_effect=_fake_reshape)
        yield {"analyze": analyze, "reshape": reshape}


def _post_draft(client, **data):
    return client.post(DRAFT_PATH, files={"audio": ("visit.wav", _wav(), "audio/wav")}, data=data)


def _all_sentences(body):
    return [sentence for section in body["sections"].values() for sentence in section["sentences"]]


def test_draft_returns_transcript_ids_and_soap_note_fields(client, downstream):
    response = _post_draft(client)
    assert response.status_code == 200, response.text
    body = response.json()

    transcript = body["transcript"]
    assert [item["id"] for item in transcript] == [f"s{i}" for i in range(1, 9)]
    assert transcript[0]["speaker"] == "doctor"
    assert transcript[1]["speaker"] == "patient"
    assert transcript[1]["start_ms"] == 2000 and transcript[1]["end_ms"] == 6000
    assert transcript[7]["lang"] == "mixed"

    assert tuple(body["soap_note"]) == SOAP_NOTE_FIELDS
    soap = body["soap_note"]
    assert soap["ChiefComplaint"] == "I have had a sore throat and fever for three days."
    assert "Review of systems:" in soap["PhysicalExamination"]
    assert "On examination the throat is red" in soap["PhysicalExamination"]
    assert "tonsillitis" in soap["Assessments"]
    assert "azithromycin 500 mg" in soap["TreatmentPlans"]
    assert soap["SurgicalHistory"] is None

    sent = json.loads(downstream["reshape"].calls.last.request.content)
    assert "view_ids" not in sent
    assert {f["transform"] for f in sent["views"][0]["fields"]} == {"direct"}

    known = {item["id"] for item in transcript}
    for sentence in _all_sentences(body):
        assert sentence["segment_ids"] and set(sentence["segment_ids"]) <= known
    for item in body["sections"]["assessment_plan"]["sentences"]:
        assert item["part"] in {"assessment", "plan"}
        assert item["text"].startswith("Acute tonsillitis, unspecified:")

    dx = body["diagnoses"]
    assert dx[0]["icd10"] == "J03.90" and dx[0]["rank"] == "primary" and dx[0]["suspected"] is True
    follow_up = next(order for order in body["orders"] if order["kind"] == "follow_up")
    assert follow_up["payload"]["booked"] is False and follow_up["payload"]["date"]
    assert body["instructions"]["language"] == "english"
    assert body["instructions"]["segment_ids"] == ["s6", "s7"]
    assert isinstance(body["elapsed_ms"], int)


def test_draft_json_base64_forwards_auth_headers(client, downstream):
    response = client.post(
        DRAFT_PATH,
        json={"audio_base64": base64.b64encode(_wav()).decode("ascii"), "note_form": "bullets"},
        headers={"X-API-Key": "key-1", "X-Clinician-Id": "dr-smith"},
    )
    assert response.status_code == 200, response.text
    forwarded = downstream["analyze"].calls.last.request.headers
    assert forwarded["X-API-Key"] == "key-1"
    assert forwarded["X-Clinician-Id"] == "dr-smith"
    assert response.json()["soap_note"]["HPI"].startswith("- ")


def test_sentence_without_segment_id_is_absent(client, downstream, monkeypatch):
    def fake_draft(transcript, options):
        return {
            "sections": {
                "hpi": {
                    "sentences": [
                        {"text": "Sore throat for three days.", "segment_ids": ["s2"]},
                        {"text": "Patient smokes ten cigarettes a day.", "segment_ids": []},
                        {"text": "Recent travel abroad.", "segment_ids": ["s99"]},
                        {"text": "No allergies known."},
                    ]
                }
            },
            "diagnoses": [{"label": "Hypertension", "icd10": "I10", "segment_ids": []}],
            "orders": [{"kind": "lab", "payload": {"test": "CBC"}, "segment_ids": []}],
            "mentions": [{"kind": "allergy", "text": "Sulfa allergy", "segment_ids": ["s42"]}],
            "instructions": {"text": "Drink fluids.", "segment_ids": []},
        }

    monkeypatch.setattr(ambient_stub, "stub_draft", fake_draft)
    response = _post_draft(client)
    assert response.status_code == 200, response.text
    body = response.json()

    texts = [sentence["text"] for sentence in _all_sentences(body)]
    assert texts == ["Sore throat for three days."]
    assert body["sections"]["hpi"]["sentences"][0]["sentence_id"] == "hpi-1"
    assert body["soap_note"]["HPI"] == "Sore throat for three days."
    assert body["diagnoses"] == [] and body["orders"] == [] and body["mentions"] == []
    assert body["instructions"] == {"language": "english", "text": "", "segment_ids": []}
    sent = downstream["reshape"].calls.last.request.content.decode("utf-8")
    assert "cigarettes" not in sent and "travel" not in sent


def test_low_confidence_dose_is_flagged(client, downstream):
    body = _post_draft(client).json()
    flags = {(flag["kind"], flag["text"]): flag["segment_ids"] for flag in body["flags"]}
    assert flags[("dose", "500 mg")] == ["s6"]
    assert flags[("drug_name", "azithromycin")] == ["s6"]
    assert all(seg_ids == ["s6"] for seg_ids in flags.values())

    plan = next(s for s in body["sections"]["assessment_plan"]["sentences"] if "azithromycin" in s["text"])
    assert plan["low_confidence"] is True
    exam = body["sections"]["physical_exam"]["sentences"][0]
    assert exam["low_confidence"] is False
    medication = next(order for order in body["orders"] if order["kind"] == "medication")
    assert medication["payload"] == {"name": "azithromycin", "dose": "500 mg"}


def test_allergy_mention_requires_confirmation(client, downstream):
    body = _post_draft(client).json()
    allergies = [mention for mention in body["mentions"] if mention["kind"] == "allergy"]
    assert allergies and allergies[0]["segment_ids"] == ["s3"]
    assert all(mention["confirm_required"] is True for mention in body["mentions"])


def test_unknown_icd10_code_is_omitted(client, downstream, monkeypatch):
    def fake_draft(transcript, options):
        return {
            "sections": {},
            "diagnoses": [
                {"label": "Made-up condition", "icd10": "X99.999", "rank": "primary", "segment_ids": ["s5"]},
                {"label": "Acute tonsillitis", "icd10": "j03.90", "rank": "primary", "segment_ids": ["s5"]},
            ],
        }

    monkeypatch.setattr(ambient_stub, "stub_draft", fake_draft)
    body = _post_draft(client).json()
    codes = [dx["icd10"] for dx in body["diagnoses"]]
    assert codes == [None, "J03.90"]
    assert "X99.999" not in json.dumps(body)
    assert [dx["rank"] for dx in body["diagnoses"]] == ["primary", "secondary"]


def test_transcription_error_hint_must_quote_its_segment(client, downstream, monkeypatch):
    def fake_draft(transcript, options):
        return {
            "sections": {
                "assessment_plan": {
                    "sentences": [{"text": "Take azithromycin 500 mg once daily.", "segment_ids": ["s6"], "part": "plan"}]
                }
            },
            "possible_transcription_errors": [
                {"heard": "azithromycin 500 mg", "likely": "amoxicillin 500 mg", "segment_ids": ["s1", "s6"]},
                {"heard": "less than a pearl", "likely": "lisinopril", "segment_ids": ["s6"]},
                {"heard": "Good morning", "likely": "good morning", "segment_ids": ["s1"]},
            ],
        }

    monkeypatch.setattr(ambient_stub, "stub_draft", fake_draft)
    body = _post_draft(client).json()
    assert body["possible_transcription_errors"] == [
        {"heard": "azithromycin 500 mg", "likely": "amoxicillin 500 mg", "segment_ids": ["s6"]}
    ]
    assert body["sections"]["assessment_plan"]["sentences"][0]["text"] == "Take azithromycin 500 mg once daily."


def test_regenerate_returns_only_requested_section(client, downstream, monkeypatch):
    transcript = _post_draft(client).json()["transcript"]

    def fake_regenerate(segments, options, section, instruction):
        assert section == "hpi" and instruction == "add smoking history"
        return {
            "sentences": [
                {"text": "Sore throat and fever for three days.", "segment_ids": ["s2"]},
                {"text": "Smokes ten cigarettes a day.", "segment_ids": []},
            ]
        }

    monkeypatch.setattr(ambient_stub, "stub_regenerate", fake_regenerate)
    response = client.post(
        REGENERATE_PATH,
        json={"transcript": transcript, "section": "hpi", "instruction": "add smoking history"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["section"] == "hpi"
    assert [s["text"] for s in body["sentences"]] == ["Sore throat and fever for three days."]
    assert set(body["sentences"][0]) == {"sentence_id", "text", "segment_ids", "low_confidence"}
    assert body["soap_note"] == {"HPI": "Sore throat and fever for three days.", "MedicalHistory": None}
    assert body["diagnoses"] == [] and body["orders"] == [] and body["mentions"] == []
    assert body["instructions"] is None
    assert body["flags"] == []
    assert "transcript" not in body and "sections" not in body
    assert isinstance(body["elapsed_ms"], int)


def test_regenerate_assessment_plan_with_stub(client, downstream):
    transcript = _post_draft(client).json()["transcript"]
    response = client.post(
        REGENERATE_PATH,
        json={"transcript": transcript, "section": "assessment_plan", "instruction": "shorter"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body["soap_note"]) == {"Assessments", "TreatmentPlans"}
    sentences = body["sentences"]
    assert len(sentences) == 2
    assert all(s["segment_ids"] and s["part"] in {"assessment", "plan"} for s in sentences)
    assert sentences[1]["low_confidence"] is True

    assert [(dx["icd10"], dx["rank"]) for dx in body["diagnoses"]] == [("J03.90", "primary")]
    assert {order["kind"] for order in body["orders"]} == {"medication", "follow_up"}
    assert all(mention["confirm_required"] is True for mention in body["mentions"])
    assert body["instructions"]["segment_ids"] == ["s6", "s7"]
    assert {(f["kind"], f["text"]) for f in body["flags"]} == {("dose", "500 mg"), ("drug_name", "azithromycin")}


def test_regenerate_review_of_systems_keeps_a_spoken_denial(client, downstream, monkeypatch):
    transcript = [
        {
            "id": "s3",
            "speaker": "doctor",
            "lang": "en",
            "start_ms": 0,
            "end_ms": 1000,
            "text": "Any nausea, vision changes, or neck stiffness?",
            "confidence": None,
        },
        {
            "id": "s4",
            "speaker": "patient",
            "lang": "en",
            "start_ms": 1000,
            "end_ms": 3000,
            "text": "No nausea. Light bothers me a little.",
            "confidence": None,
        },
    ]
    monkeypatch.setenv("USE_LLM_STUB", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    reload_settings()

    async def nested(**kwargs):
        return {
            "sections": {
                "review_of_systems": {
                    "sentences": [
                        {"text": "Neurological: No vision changes or neck stiffness.", "segment_ids": ["s3"]},
                        {"text": "Gastrointestinal: No nausea.", "segment_ids": ["s4"]},
                    ]
                }
            }
        }

    monkeypatch.setattr("app.services.ambient_draft.complete_json", nested)
    kept = client.post(
        REGENERATE_PATH,
        json={"transcript": transcript, "section": "review_of_systems", "instruction": "add vision changes and neck stiffness"},
    )
    assert kept.status_code == 200, kept.text
    body = kept.json()
    assert [sentence["text"] for sentence in body["sentences"]] == ["Gastrointestinal: No nausea."]
    assert body["sentences"][0]["segment_ids"] == ["s4"]
    assert "No nausea" in body["soap_note"]["PhysicalExamination"]
    assert body["record"]["clinical_visit"]["physicalExaminationSummery"]

    async def empty(**kwargs):
        return {"sections": {"review_of_systems": {"sentences": []}}}

    monkeypatch.setattr("app.services.ambient_draft.complete_json", empty)
    filled = client.post(
        REGENERATE_PATH,
        json={"transcript": transcript, "section": "review_of_systems"},
    ).json()
    assert [sentence["text"] for sentence in filled["sentences"]] == ["Gastrointestinal: No nausea."]


def test_regenerate_hpi_does_not_take_a_review_denial(client, downstream, monkeypatch):
    transcript = [
        {
            "id": "s2",
            "speaker": "patient",
            "lang": "en",
            "start_ms": 0,
            "end_ms": 1000,
            "text": "I have had a three-day frontal headache. No fever, but it is worse in the afternoon.",
            "confidence": None,
        },
        {
            "id": "s4",
            "speaker": "patient",
            "lang": "en",
            "start_ms": 1000,
            "end_ms": 2000,
            "text": "No nausea. Light bothers me a little.",
            "confidence": None,
        },
    ]
    monkeypatch.setenv("USE_LLM_STUB", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    reload_settings()

    async def model(**kwargs):
        return {
            "sentences": [
                {
                    "text": "The patient reports a three-day frontal headache, worse in the afternoon, with no fever.",
                    "segment_ids": ["s2"],
                },
                {"text": "Light bothers the patient a little.", "segment_ids": ["s4"]},
            ]
        }

    monkeypatch.setattr("app.services.ambient_draft.complete_json", model)
    body = client.post(REGENERATE_PATH, json={"transcript": transcript, "section": "hpi"}).json()
    texts = [sentence["text"] for sentence in body["sentences"]]
    assert "No nausea." not in texts
    assert any("frontal headache" in text for text in texts)
    assert any("Light bothers" in text for text in texts)


def test_regenerate_scopes_flags_to_the_section(client, downstream):
    transcript = _post_draft(client).json()["transcript"]
    body = client.post(REGENERATE_PATH, json={"transcript": transcript, "section": "physical_exam"}).json()
    assert [s["segment_ids"] for s in body["sentences"]] == [["s4"]]
    assert body["flags"] == []


def test_regenerate_drops_unknown_icd10_code(client, downstream, monkeypatch):
    transcript = _post_draft(client).json()["transcript"]

    def fake_regenerate(segments, options, section, instruction):
        return {
            "sentences": [{"text": "Acute tonsillitis: possibly viral.", "segment_ids": ["s5"], "part": "assessment"}],
            "diagnoses": [
                {"label": "Acute tonsillitis", "icd10": "J03.90", "segment_ids": ["s5"]},
                {"label": "Invented", "icd10": "Q99.999", "segment_ids": ["s5"]},
                {"label": "Unsourced", "icd10": "I10", "segment_ids": []},
            ],
        }

    monkeypatch.setattr(ambient_stub, "stub_regenerate", fake_regenerate)
    body = client.post(REGENERATE_PATH, json={"transcript": transcript, "section": "assessment_plan"}).json()
    assert [(dx["label"], dx["icd10"]) for dx in body["diagnoses"]] == [("Acute tonsillitis", "J03.90"), ("Invented", None)]


def test_patient_context_used_false_when_omitted(client, downstream):
    assert _post_draft(client).json()["patient_context_used"] is False

    with_context = _post_draft(
        client,
        patient_context=json.dumps({"chronic_diseases": ["Essential (primary) hypertension"], "allergies": ["penicillin"]}),
    )
    body = with_context.json()
    assert body["patient_context_used"] is True
    assert all(dx["icd10"] != "I10" for dx in body["diagnoses"])


def test_unconfigured_note_model_fails_before_convoscribe(client, downstream, monkeypatch):
    monkeypatch.setenv("USE_LLM_STUB", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    reload_settings()
    response = _post_draft(client)
    assert response.status_code == 503
    assert "OPENAI_API_KEY" in response.json()["detail"]
    assert not downstream["analyze"].called


def test_regenerate_returns_error_when_openai_call_fails(client, downstream, monkeypatch):
    transcript = _post_draft(client).json()["transcript"]
    monkeypatch.setenv("USE_LLM_STUB", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    reload_settings()

    missing = client.post(
        REGENERATE_PATH,
        json={"transcript": transcript, "section": "hpi", "instruction": "shorter"},
    )
    assert missing.status_code == 503
    assert "OPENAI_API_KEY" in missing.json()["detail"]

    async def rejected(**kwargs):
        raise HTTPException(status_code=502, detail="Ambient note model failed: AuthenticationError")

    monkeypatch.setenv("OPENAI_API_KEY", "sk-bad")
    reload_settings()
    monkeypatch.setattr("app.services.ambient_draft.complete_json", rejected)
    rejected_response = client.post(
        REGENERATE_PATH,
        json={"transcript": transcript, "section": "assessment_plan", "instruction": "shorter"},
    )
    assert rejected_response.status_code == 502
    assert "AuthenticationError" in rejected_response.json()["detail"]

    async def other_failure(**kwargs):
        raise HTTPException(status_code=502, detail="Ambient note model failed: APIConnectionError")

    monkeypatch.setattr("app.services.ambient_draft.complete_json", other_failure)
    other = client.post(REGENERATE_PATH, json={"transcript": transcript, "section": "hpi"})
    assert other.status_code == 502
    assert "APIConnectionError" in other.json()["detail"]


def test_invalid_note_option_422(client, downstream):
    response = _post_draft(client, specialty="cardiology")
    assert response.status_code == 422


def test_draft_asks_convoscribe_for_transcript_only(client, downstream):
    response = _post_draft(client)
    assert response.status_code == 200, response.text
    sent = downstream["analyze"].calls.last.request.content
    assert b'name="purpose"\r\n\r\ntranscript_only' in sent


def test_question_only_segment_is_not_evidence(client, downstream, monkeypatch):
    def fake_draft(transcript, options):
        return {
            "sections": {
                "review_of_systems": {
                    "sentences": [
                        {"text": "No vision changes or neck stiffness reported.", "segment_ids": ["s1"]},
                        {"text": "Respiratory: no cough.", "segment_ids": ["s1", "s3"]},
                    ]
                },
            },
            "diagnoses": [{"label": "Migraine", "icd10": "G43.909", "segment_ids": ["s1"]}],
        }

    monkeypatch.setattr(ambient_stub, "stub_draft", fake_draft)
    body = _post_draft(client).json()
    ros = body["sections"]["review_of_systems"]["sentences"]
    assert [sentence["text"] for sentence in ros] == ["Respiratory: no cough."]
    assert ros[0]["segment_ids"] == ["s1", "s3"]
    assert body["diagnoses"] == []


def test_medication_frequency_and_one_heading_per_diagnosis(client, downstream, monkeypatch):
    def fake_draft(transcript, options):
        label = "Acute tonsillitis, unspecified"
        return {
            "sections": {
                "assessment_plan": {
                    "sentences": [
                        {"text": f"{label}: possibly viral.", "segment_ids": ["s5"], "part": "assessment"},
                        {"text": f"{label}: azithromycin 500 mg.", "segment_ids": ["s6"], "part": "plan"},
                        {"text": f"{label}: follow up in 1 week.", "segment_ids": ["s7"], "part": "plan"},
                    ]
                }
            },
            "orders": [
                {
                    "kind": "medication",
                    "payload": {"name": "azithromycin", "dose": "500 mg", "route": "once daily"},
                    "segment_ids": ["s6"],
                }
            ],
        }

    monkeypatch.setattr(ambient_stub, "stub_draft", fake_draft)
    body = _post_draft(client).json()
    payload = body["orders"][0]["payload"]
    assert payload["frequency"] == "once daily" and payload["route"] is None
    assert body["soap_note"]["TreatmentPlans"] == (
        "Acute tonsillitis, unspecified: azithromycin 500 mg. follow up in 1 week."
    )


def test_suspected_mishearing_is_not_corrected_in_the_note(client, downstream, monkeypatch):
    def fake_draft(transcript, options):
        return {
            "sections": {
                "hpi": {"sentences": [{"text": "Takes clarithromycin 500 mg once daily.", "segment_ids": ["s6"]}]}
            },
            "instructions": {"text": "Take clarithromycin 500 mg once a day.", "segment_ids": ["s6"]},
            "possible_transcription_errors": [
                {"heard": "azithromycin 500 mg", "likely": "clarithromycin 500 mg", "segment_ids": ["s6"]}
            ],
        }

    monkeypatch.setattr(ambient_stub, "stub_draft", fake_draft)
    body = _post_draft(client).json()
    assert body["sections"]["hpi"]["sentences"][0]["text"] == "Takes azithromycin 500 mg once daily."
    assert body["instructions"]["text"] == "Take azithromycin 500 mg once a day."
    assert body["possible_transcription_errors"][0]["likely"] == "clarithromycin 500 mg"


def test_spoken_vitals_and_measurements_fill_soap_vitals(client, downstream, monkeypatch):
    def fake_draft(transcript, options):
        return {
            "sections": {
                "physical_exam": {
                    "sentences": [
                        {"text": "Throat is red, tonsils swollen.", "segment_ids": ["s4"]},
                        {"text": "Vitals: temperature 38.2 Celsius.", "segment_ids": ["s4"]},
                        {"text": "Measurements: weight 71.4 kilograms.", "segment_ids": ["s4"]},
                    ]
                }
            }
        }

    monkeypatch.setattr(ambient_stub, "stub_draft", fake_draft)
    soap = _post_draft(client).json()["soap_note"]
    assert soap["Vitals"] == "temperature 38.2 Celsius. Measurements: weight 71.4 kilograms."
    assert soap["PhysicalExamination"] == "Throat is red, tonsils swollen."


def test_history_sentence_fills_medical_history(client, downstream, monkeypatch):
    def fake_draft(transcript, options):
        return {
            "sections": {
                "hpi": {
                    "sentences": [
                        {"text": "Sore throat for three days.", "segment_ids": ["s2"]},
                        {"text": "History: allergic to penicillin.", "segment_ids": ["s3"]},
                    ]
                }
            }
        }

    monkeypatch.setattr(ambient_stub, "stub_draft", fake_draft)
    soap = _post_draft(client).json()["soap_note"]
    assert soap["HPI"] == "Sore throat for three days."
    assert soap["MedicalHistory"] == "allergic to penicillin."


def test_analyze_stage1_gets_chart_from_older_soap_output():
    from app.services.agent_service import stage1_output_from_analyze

    flat = stage1_output_from_analyze(
        {
            "summary": {
                "subjective": "Headache for 3 days.",
                "objective": "Not discussed",
                "assessment": "Tension-type headache.",
                "plan": "Ibuprofen 400 mg as needed.",
                "follow_up": "Two weeks.",
            }
        }
    )
    assert flat["chart"] == {
        "HPI": "Headache for 3 days.",
        "PhysicalExamination": "",
        "Assessments": "Tension-type headache.",
        "TreatmentPlans": "Ibuprofen 400 mg as needed. Follow-up: Two weeks.",
    }
    chart = {"HPI": "From the model."}
    assert stage1_output_from_analyze({"summary": {"subjective": "x", "chart": chart}})["chart"] == chart


# --- Asklepios record -------------------------------------------------------


def _say(downstream, lines):
    """Replace the fake ConvoScribe transcript. lines = [(speaker, text)]."""
    labels = {"doctor": "SPEAKER_00", "patient": "SPEAKER_01"}
    segments = [_segment(labels[who], i * 3.0, i * 3.0 + 2.0, text, 0.95) for i, (who, text) in enumerate(lines)]
    payload = _convoscribe_json()
    payload["raw_transcript"] = {"segments": segments}
    downstream["analyze"].mock(return_value=httpx.Response(200, json=payload))


def test_record_has_the_backend_payload_shapes(client, downstream):
    _say(
        downstream,
        [
            ("patient", "I have chest pain for two days."),
            ("doctor", "Blood pressure is 128 over 82, pulse is 78, temperature is 36.8, oxygen saturation is 98."),
            ("doctor", "Respiratory rate is 16."),
            ("doctor", "Weight is 70 kg and height is 175 cm."),
            ("patient", "The pain is 5 out of 10."),
            ("doctor", "This looks like tonsillitis."),
        ],
    )
    response = _post_draft(
        client,
        patient_context=json.dumps({"chronic_diseases": ["Hypertension"]}),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    record = body["record"]

    assert record["vital_sign"] == {
        "patientId": None,
        "encounterId": None,
        "bloodPressureSystolic": 128,
        "bloodPressureDiastolic": 82,
        "measurementSite": None,
        "heartRate": 78,
        "temperature": 36.8,
        "oxygenSaturation": 98,
        "respiratoryRate": 16,
        "fastingBloodGlucose": None,
        "fluidStatus": None,
        "edema": None,
        "urineOutput": None,
        "isTriage": False,
        "isActive": True,
        "notes": None,
    }
    assert record["body_measurements"] == {
        "patientId": None,
        "encounterId": None,
        "weight": 70,
        "height": 175,
        "headCircumference": None,
        "isActive": True,
    }
    assert record["pain_assessment"]["painLevel"] == "LEVEL_5"
    assert record["pain_assessment"]["painAssessmentType"] == "NUMERIC"
    assert record["pain_assessment"]["painDegree"] is None  # never derived from the score

    nursing = record["nursing_assessment"]
    assert nursing["reasonOfVisit"] == "I have chest pain for two days."
    assert nursing["byPatient"] is True and nursing["sourceOfInformation"] is None
    assert nursing["patientConditions"] == "Hypertension" and nursing["priorityLevel"] == "NORMAL"
    assert record["clinical_visit"]["chiefComplaint"] == "I have chest pain for two days."

    diagnosis = record["patient_diagnosis"][0]
    assert diagnosis == {
        "patientId": None,
        "encounterId": None,
        "diagnosisId": None,
        "type": "PRIMARY",
        "suspected": False,
        "major": True,
    }
    assert body["diagnoses"][0]["icd10"] == "J03.90"
    assert record["assessment"]["assessment"].startswith("Acute tonsillitis, unspecified:")

    assert body["record_status"]["vital_sign"] == "complete"
    assert body["record_status"]["body_measurements"] == "complete"
    assert body["record_status"]["pain_assessment"] == "partial"
    assert body["missing_required"] == {"pain_assessment": ["painDegree"]}
    assert body["record_evidence"]["vital_sign.heartRate"] == ["s2"]
    assert body["record_evidence"]["vital_sign.respiratoryRate"] == ["s3"]
    assert body["record_evidence"]["nursing_assessment.reasonOfVisit"] == ["s1"]
    assert body["record_evidence"]["patient_diagnosis.0"] == ["s6"]


def test_suggest_icd10_false_returns_no_diagnosis_codes(client, downstream):
    body = _post_draft(client, suggest_icd10="false").json()
    assert body["diagnoses"] == []
    assert body["record"]["patient_diagnosis"] == []
    assert body["record_status"]["patient_diagnosis"] == "empty"
    assert "tonsillitis" in body["soap_note"]["Assessments"]

    transcript = _post_draft(client).json()["transcript"]
    regenerated = client.post(
        REGENERATE_PATH,
        json={"transcript": transcript, "section": "assessment_plan", "suggest_icd10": False},
    ).json()
    assert regenerated["diagnoses"] == []
    assert regenerated["record"]["patient_diagnosis"] == []


def test_suggest_orders_false_returns_no_order_suggestions(client, downstream):
    body = _post_draft(client, suggest_orders="false").json()
    assert body["orders"] == []
    assert "azithromycin 500 mg" in body["soap_note"]["TreatmentPlans"]

    transcript = _post_draft(client).json()["transcript"]
    regenerated = client.post(
        REGENERATE_PATH,
        json={"transcript": transcript, "section": "assessment_plan", "suggest_orders": False},
    ).json()
    assert regenerated["orders"] == []
    assert "azithromycin" in regenerated["soap_note"]["TreatmentPlans"]



def test_record_ids_are_null_when_not_sent(client, downstream):
    _say(downstream, [("patient", "I have a headache."), ("doctor", "Pulse is 70.")])
    record = _post_draft(client).json()["record"]
    assert record["vital_sign"]["patientId"] is None and record["vital_sign"]["encounterId"] is None
    assert record["nursing_assessment"]["patientConditions"] is None


def test_record_drops_values_that_were_not_said_or_are_implausible(client, downstream, monkeypatch):
    _say(
        downstream,
        [
            ("doctor", "Any swelling in your legs?"),
            ("doctor", "Pulse is 78."),
            ("doctor", "Height is 1.75 m."),
            ("doctor", "Respiratory rate is 160."),
            ("doctor", "Blood pressure is 80 over 120."),
            ("doctor", "Pain is 11."),
        ],
    )

    def cite(value, *ids):
        return {"value": value, "segment_ids": list(ids)}

    def fake_draft(transcript, options):
        return {
            "record": {
                "vital_sign": {
                    "heartRate": cite(80, "s2"),  # 80 was not said
                    "temperature": cite(38, "s2"),  # not said
                    "oxygenSaturation": cite(98),  # no evidence
                    "edema": cite("NONE", "s1"),  # only a question
                    "fluidStatus": cite("SOAKED", "s2"),  # not a backend value
                    "respiratoryRate": cite(160, "s4"),  # said, but not plausible
                    "bloodPressureSystolic": cite(80, "s5"),  # swapped pair
                    "bloodPressureDiastolic": cite(120, "s5"),
                },
                "body_measurements": {"height": cite(1.75, "s3"), "weight": cite(70, "s99")},
                "pain_assessment": {"painLevel": cite(11, "s6")},
            }
        }

    monkeypatch.setattr(ambient_stub, "stub_draft", fake_draft)
    body = _post_draft(client).json()
    vital = body["record"]["vital_sign"]
    assert vital["heartRate"] == 78  # "Pulse is 78" was said; the model's 80 was not
    assert vital["bloodPressureSystolic"] is None and vital["bloodPressureDiastolic"] is None  # 80 over 120 is reversed
    assert vital["respiratoryRate"] is None and vital["temperature"] is None and vital["oxygenSaturation"] is None
    assert body["record_status"]["vital_sign"] == "partial"
    assert body["record"]["pain_assessment"] is None
    assert body["record"]["body_measurements"]["height"] == 175  # metres to centimetres, exactly
    assert body["record"]["body_measurements"]["weight"] is None
    assert body["missing_required"]["body_measurements"] == ["weight"]
    assert body["record_evidence"]["vital_sign.heartRate"] == ["s2"]
    assert body["record_evidence"]["body_measurements.height"] == ["s3"]


def test_regenerate_record_covers_only_its_section(client, downstream, monkeypatch):
    transcript = _post_draft(client).json()["transcript"]

    def fake_regenerate(segments, options, section, instruction):
        return {"sentences": [{"text": "Sore throat and fever for three days.", "segment_ids": ["s2"]}]}

    monkeypatch.setattr(ambient_stub, "stub_regenerate", fake_regenerate)
    body = client.post(REGENERATE_PATH, json={"transcript": transcript, "section": "hpi"}).json()
    assert body["record"] == {"clinical_visit": {"historyOfPresentIllness": "Sore throat and fever for three days."}}
    assert body["record_evidence"] == {"clinical_visit.historyOfPresentIllness": ["s2"]}



def test_regenerate_assessment_plan_record(client, downstream):
    transcript = _post_draft(client).json()["transcript"]
    body = client.post(REGENERATE_PATH, json={"transcript": transcript, "section": "assessment_plan"}).json()
    assert set(body["record"]) == {"assessment", "plan_of_care", "patient_diagnosis"}
    assert body["record"]["patient_diagnosis"][0]["type"] == "PRIMARY"
    assert set(body["record"]["plan_of_care"]) == {"patientId", "encounterId", "treatmentPlan"}


def test_asklepios_enum_and_number_rules():
    from app.clinical import asklepios

    texts = {"s1": "Mild pain, left arm. Sugar 95 fasting. Temperature 98.6.", "s2": "Is it getting worse?"}

    def cite(value, *ids):
        return {"value": value, "segment_ids": list(ids)}

    raw = {
        "vital_sign": {
            "measurementSite": cite("left arm", "s1"),
            "fastingBloodGlucose": cite(95, "s1"),
            "temperature": cite(98.6, "s1"),  # Fahrenheit: out of range, dropped
            "edema": cite("MILD", "s2"),  # question only
        },
        "pain_assessment": {"painDegree": cite("mild", "s1"), "painLevel": cite("LEVEL_5", "s1")},
    }
    values, evidence = asklepios.clean_record(raw, texts, {"s2"}, asklepios.DRAFT_MODEL_GROUPS)
    assert values["vital_sign"] == {"measurementSite": "Upper Arm", "fastingBloodGlucose": "95"}
    assert values["pain_assessment"] == {"painDegree": "MILD_MINOR"}  # 5 was not said in s1
    assert "vital_sign.edema" not in evidence and "vital_sign.temperature" not in evidence

    lov_texts = {"s1": "Aching pain in the forearm. She walked in."}
    lov = {
        "vital_sign": {"measurementSite": cite("6862999602450259", "s1")},
        "pain_assessment": {"painPattern": cite("PAIN_PAT_ACH", "s1")},
        "nursing_assessment": {"modeOfArrival": cite("WALK_IN", "s1")},
    }
    values, _ = asklepios.clean_record(lov, lov_texts, set(), asklepios.DRAFT_MODEL_GROUPS)
    assert values["vital_sign"]["measurementSite"] == "Forearm"  # the word, not the numeric key
    assert values["pain_assessment"] == {"painPattern": "Aching"}
    assert values["nursing_assessment"] == {"modeOfArrival": "AMBULATORY"}
    dropped = {"pain_assessment": {"painPattern": cite("INTERMITTENT", "s1")}}
    assert "pain_assessment" not in asklepios.clean_record(dropped, lov_texts, set(), asklepios.DRAFT_MODEL_GROUPS)[0]


def test_omitted_exam_findings_and_dictated_history_are_added():
    from app.models.schemas import NoteOptions, TranscriptItem
    from app.services.ambient_draft import enforce_evidence, fill_omitted_findings, soap_source

    def line(seg_id, speaker, text):
        return TranscriptItem(id=seg_id, speaker=speaker, start_ms=0, end_ms=1, text=text)

    transcript = [
        line("s2", "patient", "I have had a 3 day frontal headache; no fever, but it is worse in the afternoon."),
        line("s4", "patient", "No nausea. Light bothers me a little. My daughter says I have not been eating well since yesterday."),
        line(
            "s7",
            "patient",
            "Let me examine you. You are alert and neurologically normal. No fever on my touch. "
            "I will record your vitals now. Temperature 36.8 Celsius. Blood pressure 122 over 78. Pulse 72.",
        ),
        line("s8", "patient", "The pain is mostly a dull ache, about a 2 when I am resting."),
        line(
            "s9",
            "doctor",
            "For measurements: Weight 71.4 kilograms. Head circumference 55 centimeters. Note.--Weight taken after shoes removed. "
            "Patient reports recent appetite loss. Summary for your chart.--3 day tension type headache without red flags. "
            "Plan is ibuprofen as needed, rest, and fluids.",
        ),
        line("s11", "doctor", "Not to day; return sooner if you develop fever, the worst headache of your life, or weakness on 1 side. The nurse will give you written instructions."),
        line("s12", "patient", "Thank you, doctor."),
    ]
    raw = {
        "sections": {
            "chief_complaint": {
                "sentences": [
                    {
                        "text": "I have had a 3 day frontal headache; no fever, but it is worse in the afternoon.",
                        "segment_ids": ["s2"],
                    }
                ]
            },
            "hpi": {
                "sentences": [
                    {"text": "Light bothers the patient a little.", "segment_ids": ["s4"]},
                    {
                        "text": "Daughter reports the patient has not been eating well since yesterday.",
                        "segment_ids": ["s4"],
                    },
                ]
            },
            "review_of_systems": {
                "sentences": [
                    {"text": "Neurological: No nausea, but light bothers the patient a little.", "segment_ids": ["s4"]}
                ]
            },
            "physical_exam": {
                "sentences": [
                    {
                        "text": "Vitals: Temperature 36.8 Celsius, blood pressure 122 over 78, pulse 72, pain score 2 out of 10.",
                        "segment_ids": ["s7"],
                    },
                    {
                        "text": "Measurements: Weight 71.4 kilograms. Weight taken after shoes removed.",
                        "segment_ids": ["s9"],
                    },
                ]
            },
            "assessment_plan": {
                "sentences": [
                    {
                        "text": "Tension-type headache: 3 day tension type headache without red flags.",
                        "segment_ids": ["s9"],
                        "part": "assessment",
                    },
                    {
                        "text": "Tension-type headache: Plan is ibuprofen as needed, rest, and fluids.",
                        "segment_ids": ["s9"],
                        "part": "plan",
                    },
                ]
            },
        },
        "instructions": {
            "text": "Return sooner if you develop fever, the worst headache of your life, or weakness on one side.",
            "segment_ids": ["s11"],
        },
        "record": {"pain_assessment": {"painDescription": {"value": "dull ache", "segment_ids": ["s8"]}}},
    }
    parts = enforce_evidence(fill_omitted_findings(raw, transcript), transcript, NoteOptions())
    exam = " ".join(sentence.text for sentence in parts.sections["physical_exam"])
    hpi = " ".join(sentence.text for sentence in parts.sections["hpi"])
    everything = " ".join(sentence.text for section in parts.sections.values() for sentence in section)
    assert "alert and neurologically normal" in exam
    assert "No fever on my touch" in exam
    assert "appetite loss" in hpi
    assert "Let me examine" not in everything
    assert "I will record" not in everything
    assert "Thank you" not in everything
    assert "Not today" not in everything
    assert "Not to day" not in everything
    returns = [sentence.text for sentence in parts.sections["assessment_plan"] if "return sooner" in sentence.text.lower()]
    assert returns == ["return sooner if you develop fever, the worst headache of your life, or weakness on 1 side."]
    assert parts.measured["body_measurements"]["headCircumference"] == 55
    assert everything.count("122") == 1
    soap = soap_source(parts.sections, note_form="prose", note_language="english")
    assert "alert and neurologically normal" in soap["PhysicalExamination"]
    assert "No fever on my touch" in soap["PhysicalExamination"]
    assert "appetite loss" in soap["HPI"]
    assert "122" not in soap["PhysicalExamination"]


def test_unspoken_negatives_are_removed_and_pain_words_stay():
    from app.models.schemas import NoteOptions, TranscriptItem
    from app.services.ambient_draft import enforce_evidence

    def line(seg_id, speaker, text):
        return TranscriptItem(id=seg_id, speaker=speaker, start_ms=0, end_ms=1, text=text)

    transcript = [
        line("s3", "doctor", "Any nausea, vision changes or neck stiffness?"),
        line("s4", "patient", "No nausea; light bothers me a little."),
        line("s8", "patient", "The pain is mostly a dull ache, about a 2 when I am resting."),
        line("s9", "doctor", "3 day tension type headache without red flags."),
    ]
    raw = {
        "sections": {
            "review_of_systems": {
                "sentences": [
                    {
                        "text": "Neurological: No nausea, no vision changes, no neck stiffness.",
                        "segment_ids": ["s3", "s4"],
                    }
                ]
            },
            "assessment_plan": {
                "sentences": [
                    {
                        "text": "Tension-type headache: 3 day tension type headache without red flags.",
                        "segment_ids": ["s9"],
                        "part": "assessment",
                    }
                ]
            },
        },
        "record": {"pain_assessment": {"painPattern": {"value": "Dull", "segment_ids": ["s8"]}}},
    }
    parts = enforce_evidence(raw, transcript, NoteOptions())
    ros = parts.sections["review_of_systems"][0].text
    assert ros == "Neurological: No nausea."
    assert "vision" not in ros and "neck" not in ros
    assert "without red flags" in parts.sections["assessment_plan"][0].text
    assert parts.measured["pain_assessment"]["painDescription"] == "dull ache"
    assert parts.measured_evidence["pain_assessment.painDescription"] == ["s8"]

    named = enforce_evidence(
        {
            "sections": {
                "physical_exam": {"sentences": [{"text": "I am dr Patel.", "segment_ids": ["s1"]}]},
                "review_of_systems": {
                    "sentences": [
                        {"text": "Neurological: No nausea, light sensitivity.", "segment_ids": ["s4"]}
                    ]
                },
            }
        },
        [
            TranscriptItem(id="s1", speaker="doctor", start_ms=0, end_ms=1, text="Good morning. I am dr Patel. What brings you in today?"),
            TranscriptItem(id="s4", speaker="patient", start_ms=0, end_ms=1, text="No nausea. Light bothers me a little."),
        ],
        NoteOptions(),
    )
    assert named.sections["physical_exam"] == []
    assert named.sections["review_of_systems"][0].text == "Neurological: No nausea."


def test_chart_only_words_and_pasted_transcript_lines_are_dropped():
    from app.models.schemas import NoteOptions, PatientContext, TranscriptItem
    from app.services.ambient_draft import enforce_evidence

    def line(seg_id, speaker, text):
        return TranscriptItem(id=seg_id, speaker=speaker, start_ms=0, end_ms=1, text=text)

    transcript = [
        line("s2", "patient", "Good morning, my name is Sarah Johnson, I have been having a headache for 3 days."),
        line(
            "s10",
            "patient",
            "I can find blood pressure, I take him a bit on 5 million every morning, I have no medication allergies.",
        ),
        line(
            "s13",
            "doctor",
            "I will check your vital signs. Your temperature is 36.7 degrees Celsius, blood pressure is 128 over 82, pulse is 76.",
        ),
    ]
    raw = {
        "sections": {
            "chief_complaint": {"sentences": [{"text": "Headache for 3 days.", "segment_ids": ["s2"]}]},
            "hpi": {
                "sentences": [
                    {
                        "text": "Good morning, my name is Sarah Johnson, I have been having a headache for 3 days.",
                        "segment_ids": ["s2"],
                    },
                    {
                        "text": "History: Essential (primary) hypertension; takes lisinopril 10 mg once daily.",
                        "segment_ids": ["s10"],
                    },
                    {
                        "text": "I can find blood pressure, I take him a bit on 5 million every morning, I have no medication allergies.",
                        "segment_ids": ["s10"],
                    },
                ]
            },
            "physical_exam": {
                "sentences": [
                    {
                        "text": "Vitals: temperature 36.7 degrees Celsius, blood pressure 128 over 82, pulse 76.",
                        "segment_ids": ["s13"],
                    },
                    {
                        "text": "I will check your vital signs. Your temperature is 36.7 degrees Celsius, blood pressure is 128 over 82, pulse is 76.",
                        "segment_ids": ["s13"],
                    },
                ]
            },
        },
        "mentions": [{"kind": "allergy", "text": "penicillin", "segment_ids": ["s10"]}],
        "orders": [{"kind": "medication", "payload": {"name": "lisinopril", "dose": "10 mg"}, "segment_ids": ["s10"]}],
    }
    parts = enforce_evidence(
        raw,
        transcript,
        NoteOptions(
            patient_context=PatientContext(
                chronic_diseases=["Essential (primary) hypertension"],
                active_medications=["lisinopril 10 mg once daily"],
                allergies=["penicillin"],
            )
        ),
    )
    hpi = [sentence.text for sentence in parts.sections["hpi"]]
    exam = [sentence.text for sentence in parts.sections["physical_exam"]]
    assert hpi == [
        "I can find blood pressure, I take him a bit on 5 million every morning, I have no medication allergies."
    ]
    assert exam == ["Vitals: temperature 36.7 degrees Celsius, blood pressure 128 over 82, pulse 76."]
    assert parts.mentions == []
    assert parts.orders == []
