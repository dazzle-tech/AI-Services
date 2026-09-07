"""Integration tests for matching ORDisplayPlugin window paths."""

import base64
import io
import json
import wave

import httpx
import pytest
import respx

from app.core.config import settings
from app.core.window_registry import WINDOWS

TIME_OUT_PATH = "/api/v1/windows/nursing/time-out"


def _make_silent_wav(duration_seconds: float = 1.0, sample_rate: int = 16000) -> bytes:
    num_frames = int(duration_seconds * sample_rate)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"\x00\x00" * num_frames)
    return buffer.getvalue()


def _transcribe_json(window_id="nursing_time_out"):
    return {
        "case_id": "case-1",
        "window_id": window_id,
        "role": "nurse",
        "staff_id": "nurse-1",
        "text": "Time out. Team introductions done.",
        "duration_seconds": 1.0,
        "language": "en",
        "transcribed_at": "2026-09-03T10:15:00Z",
    }


def _time_out_fields():
    return {
        "checklist": [
            {
                "key": "correct_patient",
                "label": "Correct Patient",
                "checked": True,
                "note": "Confirmed by wristband",
            },
            {
                "key": "correct_procedure",
                "label": "Correct Procedure",
                "checked": True,
                "note": "Right total knee replacement",
            },
            {
                "key": "correct_site_and_side",
                "label": "Correct Site and Side",
                "checked": True,
                "note": "",
            },
            {
                "key": "correct_patient_position",
                "label": "Correct Patient Position",
                "checked": True,
                "note": "Supine",
            },
            {
                "key": "verification_of_site_markings",
                "label": "Verification of site markings",
                "checked": True,
                "note": "",
            },
            {
                "key": "availability_of_correct_implants_equipment",
                "label": "Availability of correct implants / special equipment",
                "checked": True,
                "note": "Size 4 tray open",
            },
        ],
        "staff": {
            "surgeon": {"staffId": "stf_2041", "displayName": "Dr. Omar Haddad"},
            "nurse": {"staffId": "stf_5590", "displayName": "Lina Odeh"},
            "anesthesiologist": {"staffId": None, "displayName": None},
            "anestheticNurse": {"staffId": None, "displayName": None},
        },
    }


def _intraoperative_fields():
    return {
        "operationStaff": {
            "date": "2026-09-03",
            "timeInToOperationRoom": "08:15",
            "timeOutFromOperationRoom": "10:40",
            "room": "ROOM1",
            "scrubNurse1": "Lina Odeh",
            "scrubNurse2": "Maha Saleh",
            "circulateNurse1": "Rana Zaid",
            "surgeon": "Dr. Omar Haddad",
            "surgeonAssist1": "Dr. Sami Khalil",
            "anesthesiologist": "Dr. Rami Nasser",
        },
        "anesthesia": {"type": "GENERAL"},
        "position": {"position": "SUPINE", "note": "Left arm tucked, padding at both heels"},
        "skinPreparationAndIncision": {
            "preparationSkinWith": "POVIDONE_IODINE",
            "incisionSite": "Right knee, midline anterior",
        },
        "foleyCatheter": {"na": False, "catheterSize": 16, "urineOutputCc": 250, "color": "Clear yellow"},
        "tourniquet": {
            "na": False,
            "startTime": "08:30",
            "endTime": "09:45",
            "totalDurationMinutes": 75,
            "pressureMmHg": 300,
            "site": "Right thigh",
        },
        "diathermiaAndLaser": {
            "na": False,
            "electroSurgicalUnit": "ESU_02",
            "dispersiveElectrodeSite": "Left thigh",
            "electroRangeCutting": "30",
            "electroRangeCoagulation": "25",
            "skinConditionBefore": "Intact, no redness",
            "skinConditionAfter": "Intact",
            "note": "",
        },
        "laser": {
            "na": True,
            "pulseEnergy": None,
            "frequency": None,
            "stoneEffect": None,
            "laserFiber": None,
            "note": "",
        },
        "drains": {"na": False, "entries": []},
        "specimens": {"na": False, "entries": []},
    }


def _sign_out_fields():
    return {
        "checklist": [
            {
                "key": "name_of_surgical_invasive_procedure",
                "label": "Name of surgical/invasive procedure",
                "checked": True,
                "response": None,
                "note": "Right total knee replacement",
            },
            {
                "key": "instruments_sponge_needle_counts_completed",
                "label": "Completion of instruments, sponge and needle counts",
                "checked": True,
                "response": "YES",
                "note": "Counts correct x2",
            },
            {
                "key": "labeling_of_specimens",
                "label": "Labeling of specimens, if present labels are read aloud",
                "checked": True,
                "response": "YES",
                "note": "Two pathology labels read aloud",
            },
            {
                "key": "address_any_equipment_problems",
                "label": "Address any equipment problems",
                "checked": True,
                "response": "NO",
                "note": "",
            },
        ]
    }


def _operative_note_fields():
    return {
        "operativeDetails": {"time": "08:15", "typeOfAnesthesia": "General"},
        "operationStaff": {
            "mainSurgeon": "Dr. Omar Haddad",
            "surgeonsAssistant": "Dr. Yousef Amr",
            "surgicalStartTime": "2026-08-17T08:30:00",
            "surgicalEndTime": "2026-08-17T10:05:00",
        },
        "operationNote": "Under general anesthesia the patient was positioned supine.",
        "complication": "None",
        "estimatedBloodLossMl": 20,
    }


def _pre_eval_fields():
    return {
        "socialHistory": {
            "allergies": "Penicillin",
            "smoker": "No",
            "alcoholic": "No",
            "substanceUse": "None",
        },
        "lastMeal": {
            "food": "Light breakfast",
            "foodDate": "2026-09-02T08:00:00",
            "fluid": "Water",
            "fluidDate": "2026-09-03T22:00:00",
        },
        "previousAnesthesiaAndSurgery": {
            "previousAnesthesia": "Yes",
            "previousSurgery": "Yes",
            "difficultIntubation": "No",
            "complication": "No",
            "comments": "Appendectomy in 2018 under general anesthesia, uneventful",
        },
        "pastMedicalHistory": {
            "cardiovascular": "",
            "respiratory": "",
            "neurological": "",
            "urological": "",
            "musculoskeletal": "Chronic right knee pain",
            "psychiatric": "",
            "pregnancies": "",
            "renalDisease": "",
            "endocrine": "Type 2 diabetes, controlled",
            "hepatic": "",
            "gastrointestinal": "",
            "bloodVessel": "",
            "otherDiseases": "",
        },
        "vitalSigns": {
            "weightKg": 82,
            "bpSystolic": 128,
            "bpDiastolic": 82,
            "pulseRate": 76,
            "tempC": 36.8,
            "spo2": 98,
        },
        "clinicalExamination": {
            "cardiovascular": "Normal S1 S2, no murmurs",
            "respiratory": "Clear air entry bilaterally",
            "skin": "Intact, no lesions",
            "sensors": "",
            "neuromuscular": "",
            "gcs": None,
            "others": "",
        },
        "airwayAssessment": {
            "mallampatiClass": "",
            "openMouth": "",
            "thyromentalDistance": "",
            "dentalState": "",
            "neckMobility": "Full range",
            "others": "",
        },
        "clinicalData": {
            "chestXray": "Unremarkable",
            "ecg": "Normal sinus rhythm",
            "others": "",
        },
        "asa": {"asaClass": "2", "emergency": False},
        "preAnesthesiaOrders": {
            "orders": "NPO after midnight, continue home antihypertensives",
        },
        "preMedication": {
            "preMedication": "Midazolam 2mg IV",
            "prophylacticAntibiotic": "YES",
            "prophylacticAntibioticNote": "Cefazolin 1g IV on call to OR",
        },
        "anesthesiaPlan": {
            "typeOfAnesthesia": "General",
            "anesthesiologist": "Dr. Rami Nasser",
            "anesthesiologistResident": "",
            "date": "2026-09-03T08:30:00",
        },
    }


def _induction_fields():
    return {
        "preInductionAssessment": {
            "bpSystolic": 120,
            "bpDiastolic": 80,
            "hr": 78,
            "rr": 16,
            "o2Sat": 98,
            "npo": "YES",
            "npoDate": "2026-09-12",
            "preMedication": "YES",
            "preMedicationNote": "Midazolam 2mg IV given",
            "date": "2026-09-12T08:30:00",
        },
        "intraoperativeAnesthesia": {
            "induction": "IV induction",
            "intubation": "Endotracheal tube",
            "airway": "Cuffed ETT size 7.5",
            "position": "Supine",
            "anesthesiologistResident": "Dr. Yara Sabbagh",
            "anesthesiaTechnician": "Khaled Nimr",
        },
    }


def _observation_fields():
    return {
        "vitalSign": {
            "bpSystolic": 120,
            "bpDiastolic": 80,
            "hr": 78,
            "oxygenSupply": "2",
            "etco2": 35,
            "spo2": 98,
            "tempC": "36.8",
            "tidalVolume": "450",
            "rr": "16",
            "act": "",
            "fio2": "40",
            "rbs": "",
            "o2Air": "2",
        },
        "bloodLoss": {
            "bloodQuantity": "",
            "bloodLoss": 20,
        },
    }


def _extract_json(window_id="nursing_time_out"):
    if window_id == "nursing_time_out":
        return _time_out_fields()
    if window_id == "nursing_intraoperative":
        return _intraoperative_fields()
    if window_id == "nursing_sign_out":
        return _sign_out_fields()
    if window_id == "operative_note":
        return _operative_note_fields()
    if window_id == "anesthesia_pre_evaluation_plan":
        return _pre_eval_fields()
    if window_id == "anesthesia_induction_intraoperative":
        return _induction_fields()
    if window_id == "anesthesia_observation_drugs":
        return _observation_fields()
    return {
        "case_id": "case-1",
        "window_id": window_id,
        "fields": {"team_introductions_done": True, "notes": None},
        "confidence": "high",
        "needs_review": False,
        "missing_fields": ["notes"],
        "raw_text": "Time out. Team introductions done.",
    }


@respx.mock
def test_time_out_wav_calls_matching_display_endpoint(client):
    transcribe_url = f"{settings.orscribe_base_url}/api/v1/windows/transcribe"
    extract_url = f"{settings.ordisplay_base_url}{TIME_OUT_PATH}"

    respx.post(transcribe_url).mock(return_value=httpx.Response(200, json=_transcribe_json()))
    respx.post(extract_url).mock(return_value=httpx.Response(200, json=_extract_json()))

    files = {"audio": ("clip.wav", _make_silent_wav(), "audio/wav")}
    response = client.post(TIME_OUT_PATH, files=files)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["checklist"][0]["key"] == "correct_patient"
    assert body["staff"]["surgeon"]["staffId"] == "stf_2041"
    assert "window_id" not in body
    extract_body = json.loads(respx.calls[-1].request.content.decode("utf-8"))
    assert extract_body["text"] == "Time out. Team introductions done."
    assert extract_body["role"] == "nurse"
    assert TIME_OUT_PATH in str(respx.calls[-1].request.url)


@respx.mock
def test_time_out_without_case_id(client):
    transcribe_url = f"{settings.orscribe_base_url}/api/v1/windows/transcribe"
    extract_url = f"{settings.ordisplay_base_url}{TIME_OUT_PATH}"
    respx.post(transcribe_url).mock(return_value=httpx.Response(200, json=_transcribe_json()))
    respx.post(extract_url).mock(return_value=httpx.Response(200, json=_extract_json()))

    files = {"audio": ("clip.wav", _make_silent_wav(), "audio/wav")}
    response = client.post(TIME_OUT_PATH, files=files)
    assert response.status_code == 200
    extract_body = json.loads(respx.calls[-1].request.content.decode("utf-8"))
    assert "case_id" not in extract_body
    assert "staff_id" not in extract_body


@respx.mock
def test_orscribe_failure_502(client):
    transcribe_url = f"{settings.orscribe_base_url}/api/v1/windows/transcribe"
    respx.post(transcribe_url).mock(return_value=httpx.Response(500, text="boom"))

    files = {"audio": ("clip.wav", _make_silent_wav(), "audio/wav")}
    response = client.post(TIME_OUT_PATH, files=files)
    assert response.status_code == 502
    assert "ORScribe transcription failed" in response.json()["detail"]


@respx.mock
def test_display_failure_502(client):
    transcribe_url = f"{settings.orscribe_base_url}/api/v1/windows/transcribe"
    extract_url = f"{settings.ordisplay_base_url}{TIME_OUT_PATH}"
    respx.post(transcribe_url).mock(return_value=httpx.Response(200, json=_transcribe_json()))
    respx.post(extract_url).mock(return_value=httpx.Response(500, text="extract boom"))

    files = {"audio": ("clip.wav", _make_silent_wav(), "audio/wav")}
    response = client.post(TIME_OUT_PATH, files=files)
    assert response.status_code == 502
    assert "Field extraction failed" in response.json()["detail"]


@respx.mock
def test_health_pings_downstream(client):
    respx.get(f"{settings.orscribe_base_url}/api/v1/health").mock(
        return_value=httpx.Response(200, json={"status": "ok"})
    )
    respx.get(f"{settings.ordisplay_base_url}/api/v1/health").mock(
        return_value=httpx.Response(200, json={"status": "ok"})
    )
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["downstream"]["orscribe"] == "ok"
    assert body["downstream"]["ordisplay_plugin"] == "ok"
    assert body["status"] == "ok"


@respx.mock
def test_time_out_json_base64(client):
    transcribe_url = f"{settings.orscribe_base_url}/api/v1/windows/transcribe"
    extract_url = f"{settings.ordisplay_base_url}{TIME_OUT_PATH}"
    respx.post(transcribe_url).mock(return_value=httpx.Response(200, json=_transcribe_json()))
    respx.post(extract_url).mock(return_value=httpx.Response(200, json=_extract_json()))

    wav = _make_silent_wav()
    response = client.post(
        TIME_OUT_PATH,
        json={
            "audio_base64": base64.b64encode(wav).decode("ascii"),
            "filename": "clip.wav",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["staff"]["nurse"]["displayName"] == "Lina Odeh"


@respx.mock
@pytest.mark.parametrize("spec", list(WINDOWS), ids=[item.window_id for item in WINDOWS])
def test_each_window_path_forwards_to_same_display_path(client, spec):
    transcribe_url = f"{settings.orscribe_base_url}/api/v1/windows/transcribe"
    extract_url = f"{settings.ordisplay_base_url}{spec.display_path}"
    respx.post(transcribe_url).mock(
        return_value=httpx.Response(200, json=_transcribe_json(spec.window_id))
    )
    respx.post(extract_url).mock(
        return_value=httpx.Response(200, json=_extract_json(spec.window_id))
    )

    files = {"audio": ("clip.wav", _make_silent_wav(), "audio/wav")}
    response = client.post(spec.display_path, files=files)
    assert response.status_code == 200, response.text
    body = response.json()
    if spec.window_id == "nursing_time_out":
        assert "checklist" in body
        assert "staff" in body
    elif spec.window_id == "nursing_intraoperative":
        assert "operationStaff" in body
        assert "specimens" in body
    elif spec.window_id == "nursing_sign_out":
        assert "checklist" in body
        assert "window_id" not in body
    elif spec.window_id == "operative_note":
        assert "operationNote" in body
        assert "window_id" not in body
    elif spec.window_id == "anesthesia_pre_evaluation_plan":
        assert "asa" in body
        assert "socialHistory" in body
        assert "window_id" not in body
    elif spec.window_id == "anesthesia_induction_intraoperative":
        assert "preInductionAssessment" in body
        assert "intraoperativeAnesthesia" in body
        assert "window_id" not in body
    elif spec.window_id == "anesthesia_observation_drugs":
        assert "vitalSign" in body
        assert "bloodLoss" in body
        assert "window_id" not in body
    else:
        assert body["window_id"] == spec.window_id
    assert spec.display_path in str(respx.calls[-1].request.url)
