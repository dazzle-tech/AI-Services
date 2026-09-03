"""Tests for per-window field fill endpoints."""

import pytest

from tests.fixtures.sample_window_texts import EXPECTED_NONEMPTY, GARBLED_TEXT, SAMPLE_TEXTS, WINDOW_PATHS, WINDOW_ROLES


@pytest.mark.parametrize("window_id", list(SAMPLE_TEXTS))
def test_fill_window_from_dictation(client, window_id):
    response = client.post(
        WINDOW_PATHS[window_id],
        json={
            "case_id": "case-1",
            "role": WINDOW_ROLES[window_id],
            "text": SAMPLE_TEXTS[window_id],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    if window_id == "nursing_time_out":
        assert body["checklist"]
        assert body["staff"] is not None
        return
    if window_id == "nursing_intraoperative":
        assert body["operationStaff"]["date"] == "2026-09-03"
        assert body["anesthesia"]["type"] == "GENERAL"
        return
    if window_id == "nursing_sign_out":
        assert body["checklist"]
        return
    if window_id == "operative_note":
        assert body["operationNote"]
        return
    assert body["window_id"] == window_id
    assert body["fields"][EXPECTED_NONEMPTY[window_id]] is not None


def test_verification_of_marking_site_shape(client):
    text = SAMPLE_TEXTS["nursing_verification_of_marking_site"]
    response = client.post(
        WINDOW_PATHS["nursing_verification_of_marking_site"],
        json={"role": "nurse", "text": text},
    )
    assert response.status_code == 200
    fields = response.json()["fields"]
    assert fields["checklist"] == [
        {
            "key": "site_side_level_documented",
            "label": "Site / Side / Level documented, if applicable",
            "checked": True,
            "note": "",
        },
        {
            "key": "pre_procedural_checklist_completed",
            "label": "Pre-Procedural Check List Completed",
            "checked": True,
            "note": "",
        },
        {
            "key": "procedure_surgical_consent_completed",
            "label": "The Procedure/Surgical Consent Completed",
            "checked": True,
            "note": "Signed by patient",
        },
        {
            "key": "anesthesia_consent_completed",
            "label": "The Anesthesia Consent Completed, if applicable",
            "checked": None,
            "note": "",
        },
    ]
    assert fields["siteMarking"]["status"] == "MARKED"
    assert fields["siteMarking"]["marked"] is True
    assert "left knee" in fields["siteMarking"]["note"].lower()


@pytest.mark.parametrize(
    "text,status,marked",
    [
        ("Site is not marked because it is a single organ.", "NOT_MARKED_SINGLE_ORGAN", False),
        ("Site not marked, premature infant.", "NOT_MARKED_PREMATURE_INFANT_OR_TEETH", False),
        ("Site not marked, patient refused.", "NOT_MARKED_PATIENT_REFUSED", False),
        ("Identity confirmed only.", "NOT_STATED", None),
    ],
)
def test_site_marking_status_mapping(client, text, status, marked):
    response = client.post(
        WINDOW_PATHS["nursing_verification_of_marking_site"],
        json={"role": "nurse", "text": text},
    )
    marking = response.json()["fields"]["siteMarking"]
    assert marking["status"] == status
    assert marking["marked"] is marked


def test_time_out_shape(client):
    response = client.post(
        WINDOW_PATHS["nursing_time_out"],
        json={"role": "nurse", "text": SAMPLE_TEXTS["nursing_time_out"]},
    )
    assert response.status_code == 200
    fields = response.json()
    assert "window_id" not in fields
    assert "case_id" not in fields
    keys = [item["key"] for item in fields["checklist"]]
    assert keys == [
        "correct_patient",
        "correct_procedure",
        "correct_site_and_side",
        "correct_patient_position",
        "verification_of_site_markings",
        "availability_of_correct_implants_equipment",
    ]
    by_key = {item["key"]: item for item in fields["checklist"]}
    assert by_key["correct_patient"]["checked"] is True
    assert by_key["correct_patient"]["note"] == "Confirmed by wristband"
    assert by_key["correct_procedure"]["checked"] is True
    assert "knee" in by_key["correct_procedure"]["note"].lower()
    assert by_key["correct_site_and_side"]["checked"] is True
    assert by_key["correct_patient_position"]["note"].lower().startswith("supine")
    assert by_key["verification_of_site_markings"]["checked"] is True
    assert by_key["availability_of_correct_implants_equipment"]["label"] == (
        "Availability of correct implants / special equipment"
    )
    assert "tray" in by_key["availability_of_correct_implants_equipment"]["note"].lower()
    assert fields["staff"]["surgeon"]["staffId"] == "stf_2041"
    assert "Omar Haddad" in fields["staff"]["surgeon"]["displayName"]
    assert fields["staff"]["nurse"]["staffId"] == "stf_5590"
    assert "Lina Odeh" in fields["staff"]["nurse"]["displayName"]


def test_intraoperative_shape(client):
    response = client.post(
        WINDOW_PATHS["nursing_intraoperative"],
        json={"role": "nurse", "text": SAMPLE_TEXTS["nursing_intraoperative"]},
    )
    assert response.status_code == 200
    fields = response.json()
    assert "window_id" not in fields
    staff = fields["operationStaff"]
    assert staff["date"] == "2026-09-03"
    assert staff["timeInToOperationRoom"] == "08:15"
    assert staff["timeOutFromOperationRoom"] == "10:40"
    assert staff["room"] == "ROOM1"
    assert staff["scrubNurse1"] == "Lina Odeh"
    assert staff["scrubNurse2"] == "Maha Saleh"
    assert staff["circulateNurse1"] == "Rana Zaid"
    assert staff["surgeon"] == "Dr. Omar Haddad"
    assert staff["surgeonAssist1"] == "Dr. Sami Khalil"
    assert staff["anesthesiologist"] == "Dr. Rami Nasser"
    assert fields["anesthesia"]["type"] == "GENERAL"
    assert fields["position"]["position"] == "SUPINE"
    assert fields["position"]["note"] == "Left arm tucked, padding at both heels"
    assert fields["skinPreparationAndIncision"]["preparationSkinWith"] == "POVIDONE_IODINE"
    assert fields["skinPreparationAndIncision"]["incisionSite"] == "Right knee, midline anterior"
    assert fields["foleyCatheter"]["na"] is False
    assert fields["foleyCatheter"]["catheterSize"] == 16
    assert fields["foleyCatheter"]["urineOutputCc"] == 250
    assert fields["foleyCatheter"]["color"] == "Clear yellow"
    assert fields["tourniquet"]["pressureMmHg"] == 300
    assert fields["tourniquet"]["site"] == "Right thigh"
    assert fields["diathermiaAndLaser"]["electroSurgicalUnit"] == "ESU_02"
    assert fields["diathermiaAndLaser"]["dispersiveElectrodeSite"] == "Left thigh"
    assert fields["diathermiaAndLaser"]["skinConditionBefore"] == "Intact, no redness"
    assert fields["diathermiaAndLaser"]["skinConditionAfter"] == "Intact"
    assert fields["laser"]["na"] is True
    drain_types = [row["type"] for row in fields["drains"]["entries"]]
    assert drain_types == ["HEMOVAC", "CHEST_TUBE", "OTHERS"]
    assert fields["drains"]["entries"][0]["location"] == "Suprapatellar pouch"
    assert fields["drains"]["entries"][1]["location"] == "Right pleural cavity"
    assert fields["drains"]["entries"][2]["location"] == "Subcutaneous, lateral"
    specimen_types = [row["type"] for row in fields["specimens"]["entries"]]
    assert specimen_types == ["PATHOLOGY", "FROZEN_SECTION", "REMOVED_ORGAN_DESCRIPTION"]
    assert fields["specimens"]["entries"][2]["numberOfSamples"] == 1
    assert fields["specimens"]["entries"][2]["description"] == "Excised meniscal fragment, approx 2 cm"
    assert set(fields) >= {
        "operationStaff",
        "anesthesia",
        "position",
        "skinPreparationAndIncision",
        "foleyCatheter",
        "tourniquet",
        "diathermiaAndLaser",
        "laser",
        "drains",
        "specimens",
    }


def test_operative_note_shape(client):
    response = client.post(
        WINDOW_PATHS["operative_note"],
        json={"role": "surgeon", "text": SAMPLE_TEXTS["operative_note"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert "window_id" not in body
    assert body["operativeDetails"]["time"] == "08:15"
    assert body["operativeDetails"]["typeOfAnesthesia"] == "General"
    assert body["operationStaff"]["mainSurgeon"] == "Dr. Omar Haddad"
    assert body["operationStaff"]["surgeonsAssistant"] == "Dr. Yousef Amr"
    assert body["operationStaff"]["surgicalStartTime"] == "2026-08-17T08:30:00"
    assert body["operationStaff"]["surgicalEndTime"] == "2026-08-17T10:05:00"
    assert "midline anterior incision" in body["operationNote"].lower()
    assert body["complication"] == "None"
    assert body["estimatedBloodLossMl"] == 20


def test_sign_out_shape(client):
    response = client.post(
        WINDOW_PATHS["nursing_sign_out"],
        json={"role": "nurse", "text": SAMPLE_TEXTS["nursing_sign_out"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert "window_id" not in body
    assert len(body["checklist"]) == 4
    by_key = {item["key"]: item for item in body["checklist"]}
    assert by_key["name_of_surgical_invasive_procedure"]["checked"] is True
    assert by_key["name_of_surgical_invasive_procedure"]["response"] is None
    assert by_key["name_of_surgical_invasive_procedure"]["note"] == "Right total knee replacement"
    assert by_key["instruments_sponge_needle_counts_completed"]["response"] == "YES"
    assert by_key["instruments_sponge_needle_counts_completed"]["note"] == "Counts correct x2"
    assert by_key["labeling_of_specimens"]["response"] == "YES"
    assert by_key["labeling_of_specimens"]["note"] == "Two pathology labels read aloud"
    assert by_key["address_any_equipment_problems"]["response"] == "NO"
    assert by_key["address_any_equipment_problems"]["note"] == ""


@pytest.mark.parametrize("window_id", list(SAMPLE_TEXTS))
def test_garbled_text_needs_review(client, window_id):
    response = client.post(
        WINDOW_PATHS[window_id],
        json={"role": WINDOW_ROLES[window_id], "text": GARBLED_TEXT},
    )
    assert response.status_code == 200
    body = response.json()
    if window_id == "nursing_time_out":
        assert "checklist" in body
        assert "needs_review" not in body
        return
    if window_id == "nursing_intraoperative":
        assert "operationStaff" in body
        assert "needs_review" not in body
        return
    if window_id == "nursing_sign_out":
        assert "checklist" in body
        assert "needs_review" not in body
        return
    if window_id == "operative_note":
        assert "operationNote" in body
        assert "needs_review" not in body
        return
    assert body["needs_review"] is True


def test_extract_dispatches_by_window_name_and_role(client):
    response = client.post(
        "/api/v1/windows/extract",
        json={
            "text": SAMPLE_TEXTS["nursing_time_out"],
            "window_name": "Time Out",
            "role": "Nursing",
            "case_id": "case-1",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["window_id"] == "nursing_time_out"
    assert body["fields"][EXPECTED_NONEMPTY["nursing_time_out"]] is not None


def test_extract_unknown_window_422(client):
    response = client.post(
        "/api/v1/windows/extract",
        json={"text": "hello", "window_name": "not a window", "role": "nurse"},
    )
    assert response.status_code == 422
