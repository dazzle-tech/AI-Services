"""Acceptance chart for nurse, radiologist, and cardiologist. The OpenAI client is mocked."""
import json
import re

import pytest

from app.core.config import settings
from app.models.schemas import RoleTimelineRequest
from app.services.timeline_service import TimelineService
from tests.fixtures.acceptance_chart import ACCEPTANCE_PATIENT, CANONICAL_EVENTS, SHARED_SUMMARY
from tests.fixtures.scripted_model import ScriptedCompletions, step_names

ROLES = ("nurse", "radiologist", "cardiologist")
FORBIDDEN = (
    "infarct",
    "stemi",
    "nstemi",
    "stenosis",
    "occlusion",
    "mmhg",
    "contrast allergy",
)


def _run(script, role):
    service = TimelineService()
    service.ai_client._completions.create = script
    request = RoleTimelineRequest(
        request_id=f"acceptance-{role}",
        viewer_role=role,
        patient_data=ACCEPTANCE_PATIENT,
    )
    return service.process_request(request)


def _event(response, event_id):
    return next(event for event in response.timeline if event.event_id == event_id)


def _signature(response):
    return [
        (
            event.event_id,
            event.date,
            event.event_type,
            event.title,
            event.description,
            event.clinical_importance,
            event.source,
        )
        for event in response.timeline
    ]


def _assert_shared_chart(response):
    blob = json.dumps(response.model_dump()).lower()
    for word in FORBIDDEN:
        assert word not in blob
    assert "160/100" in blob
    troponins = [
        event for event in response.timeline
        if "troponin" in event.title.lower() or "troponin" in event.description.lower()
    ]
    assert len(troponins) == 1
    assert "0.8" in troponins[0].description
    assert "ng/ml" in troponins[0].description.lower()
    assert "high" in troponins[0].description.lower()
    assert any("shortness of breath" in event.description.lower() for event in response.timeline)
    assert any("penicillin" in event.title.lower() for event in response.timeline)
    assert any("insulin" in event.title.lower() and "active" in event.description.lower() for event in response.timeline)
    assert any("angiograph" in event.title.lower() for event in response.timeline)
    for event in response.timeline:
        if event.event_type == "medication":
            assert not re.search(r"\b(mg|units|subcutaneous|orally|bid|tid)\b", event.description, re.I)
    summary = response.clinical_summary
    assert summary == SHARED_SUMMARY
    assert "problem" in summary.lower()
    assert "58" in summary
    assert "male" in summary.lower()
    assert "successfully" not in summary.lower()
    for role_name in ROLES:
        assert role_name not in summary.lower()
    assert response.processing_metadata.model == settings.openai_model
    assert response.processing_metadata.event_count == len(response.timeline)
    assert response.processing_metadata.timestamp


def _cited(response, predicate):
    matches = []
    for highlight in response.role_highlights:
        event = _event(response, highlight.event_id)
        if predicate(event):
            matches.append((highlight, event))
    return matches


@pytest.fixture(scope="module")
def chart_responses():
    """Run the acceptance chart once per role against one mocked client."""
    script = ScriptedCompletions()
    service = TimelineService()
    service.ai_client._completions.create = script
    responses = {}
    for role in ROLES:
        responses[role] = service.process_request(
            RoleTimelineRequest(
                request_id=f"acceptance-{role}",
                viewer_role=role,
                patient_data=ACCEPTANCE_PATIENT,
            )
        )
    return responses, script


def test_acceptance_chart_is_the_same_summary_for_every_role(chart_responses):
    """The summary step does not see the role, so the summary text matches."""
    responses, script = chart_responses
    summaries = [responses[role].clinical_summary for role in ROLES]
    assert summaries[0] == summaries[1] == summaries[2] == SHARED_SUMMARY
    assert _signature(responses["nurse"]) == _signature(responses["radiologist"])
    assert _signature(responses["nurse"]) == _signature(responses["cardiologist"])

    summary_calls = [
        call for call in script.calls if "STEP: clinical_summary" in call["messages"][-1]["content"]
    ]
    timeline_calls = [
        call for call in script.calls if "STEP: timeline" in call["messages"][-1]["content"]
    ]
    assert len(summary_calls) == 3
    assert timeline_calls[0]["messages"][-1]["content"] == timeline_calls[1]["messages"][-1]["content"]
    assert summary_calls[0]["messages"][-1]["content"] == summary_calls[1]["messages"][-1]["content"]
    for call in summary_calls + timeline_calls:
        blob = "\n".join(message["content"] for message in call["messages"])
        assert "VIEWER_ROLE" not in blob
        for role_name in ROLES:
            assert role_name not in blob.lower()
        assert call["kwargs"]["model"] == settings.openai_model
        assert call["kwargs"]["temperature"] == settings.openai_temperature
    assert step_names(script) == ["timeline", "summary", "highlights"] * 3


def test_acceptance_nurse_highlight(chart_responses):
    """Nurse leads with symptoms, blood pressure, penicillin, insulin, and the troponin value."""
    response, _script = chart_responses
    nurse = response["nurse"]
    _assert_shared_chart(nurse)
    assert nurse.processing_metadata.viewer_role == "nurse"
    leads = [item for item in nurse.role_highlights if item.salience == "lead"]
    lead_events = [_event(nurse, item.event_id) for item in leads]
    assert [event.event_type for event in lead_events[:5]] == [
        "symptom",
        "vital",
        "allergy",
        "medication",
        "lab",
    ]
    assert "shortness of breath" in lead_events[0].description.lower()
    assert "chest pain" in lead_events[0].description.lower()
    assert "160/100" in lead_events[1].description
    assert "penicillin" in lead_events[2].title.lower()
    assert "insulin" in lead_events[3].title.lower()
    assert "0.8" in lead_events[4].description
    assert all(event.event_type != "procedure" for event in lead_events)
    gaps = " ".join(nurse.not_documented).lower()
    assert "vital set" in gaps
    assert "glucose is not documented" in gaps
    assert "dose is not documented" in gaps
    assert "route is not documented" in gaps
    assert "frequency is not documented" in gaps
    assert "takes none" not in gaps


def test_acceptance_radiologist_highlight(chart_responses):
    """Radiologist leads with the symptoms and records renal function as not documented."""
    response, _script = chart_responses
    radiologist = response["radiologist"]
    _assert_shared_chart(radiologist)
    assert radiologist.processing_metadata.viewer_role == "radiologist"
    first = radiologist.role_highlights[0]
    first_event = _event(radiologist, first.event_id)
    assert first.salience == "lead"
    assert "chest pain" in first_event.description.lower()
    assert "shortness of breath" in first_event.description.lower()
    gaps = " ".join(radiologist.not_documented)
    assert "Renal function (creatinine or eGFR) is not documented." in gaps
    assert "The study ordered is not documented." in gaps
    assert "Contrast reaction is not documented." in gaps
    assert "Prior imaging report is not documented." in gaps
    assert "Procedure findings are not documented." in gaps
    for highlight in radiologist.role_highlights:
        text = highlight.why_it_matters.lower()
        assert "contrast allergy" not in text
        if "penicillin" in text:
            assert "contrast" not in text


def test_acceptance_cardiologist_highlight(chart_responses):
    """Cardiologist leads with symptoms, the single troponin, and the prior angiogram."""
    response, _script = chart_responses
    cardiologist = response["cardiologist"]
    _assert_shared_chart(cardiologist)
    assert cardiologist.processing_metadata.viewer_role == "cardiologist"
    leads = [item for item in cardiologist.role_highlights if item.salience == "lead"]
    lead_events = [_event(cardiologist, item.event_id) for item in leads]
    assert lead_events[0].event_type == "symptom"
    assert "shortness of breath" in lead_events[0].description.lower()
    assert lead_events[1].event_type == "lab"
    assert "0.8" in lead_events[1].description
    assert "ng/ml" in lead_events[1].description.lower()
    assert lead_events[2].event_type == "procedure"
    assert "angiograph" in lead_events[2].title.lower()
    gaps = " ".join(cardiologist.not_documented)
    assert "ECG is not documented." in gaps
    assert "A second troponin is not documented." in gaps
    assert "The troponin reference range is not documented." in gaps
    assert "Antithrombotic therapy is not documented." in gaps
    assert "Angiogram findings are not documented." in gaps
    assert "takes none" not in gaps.lower()
    assert not re.search(r"\b(lad|rca|circumflex)\b", json.dumps(cardiologist.model_dump()), re.I)


def test_nurse_does_not_lead_with_old_angiogram_when_model_marks_it_lead():
    """An old procedure stays on the timeline and is demoted out of the nurse lead set."""

    def highlights(role, events):
        payload = compliant_from(role, events)
        if role == "nurse":
            for item in payload["role_highlights"]:
                event = next(row for row in events if row["event_id"] == item["event_id"])
                if event["event_type"] == "procedure":
                    item["salience"] = "lead"
                    item["why_it_matters"] = "Coronary angiography was completed on 2020-02-15."
            payload["role_highlights"].sort(key=lambda item: item["salience"] != "lead")
            payload["role_highlights"].insert(0, payload["role_highlights"].pop(
                next(
                    index for index, item in enumerate(payload["role_highlights"])
                    if "angiography" in item["why_it_matters"].lower()
                )
            ))
        return payload

    response = _run(ScriptedCompletions(highlight_builder=highlights), "nurse")
    assert any("angiograph" in event.title.lower() for event in response.timeline)
    procedure_ids = {
        event.event_id for event in response.timeline if event.event_type == "procedure"
    }
    procedure_highlights = [
        item for item in response.role_highlights if item.event_id in procedure_ids
    ]
    assert procedure_highlights
    assert all(item.salience == "context" for item in procedure_highlights)
    assert response.role_highlights[0].event_id not in procedure_ids


def test_cardiologist_model_cannot_add_an_infarct_or_artery_description():
    """A second sentence that diagnoses an infarct is removed. The cited event remains."""

    def highlights(role, events):
        payload = compliant_from(role, events)
        if role == "cardiologist":
            for item in payload["role_highlights"]:
                event = next(row for row in events if row["event_id"] == item["event_id"])
                if event["event_type"] == "procedure":
                    item["why_it_matters"] = (
                        "Coronary angiography was completed on 2020-02-15. "
                        "The LAD was occluded and this is an NSTEMI."
                    )
                if event["event_type"] == "lab":
                    item["why_it_matters"] = (
                        "Troponin is 0.8 ng/mL, flagged high, on 2026-03-13. "
                        "The value shows a rise and an infarct."
                    )
        return payload

    response = _run(ScriptedCompletions(highlight_builder=highlights), "cardiologist")
    blob = json.dumps(response.model_dump()).lower()
    assert "nstemi" not in blob
    assert "infarct" not in blob
    assert "occluded" not in blob
    assert "rise" not in blob
    leads = [item for item in response.role_highlights if item.salience == "lead"]
    lead_types = [_event(response, item.event_id).event_type for item in leads]
    assert "lab" in lead_types
    assert "procedure" in lead_types
    assert "0.8" in blob


def test_radiologist_model_cannot_call_penicillin_a_contrast_allergy():
    """Penicillin stays a penicillin allergy. Contrast reaction stays not documented."""

    def highlights(role, events):
        payload = compliant_from(role, events)
        if role == "radiologist":
            for item in payload["role_highlights"]:
                event = next(row for row in events if row["event_id"] == item["event_id"])
                if event["event_type"] == "allergy":
                    item["why_it_matters"] = "Penicillin is a contrast allergy."
                    item["salience"] = "lead"
        return payload

    response = _run(ScriptedCompletions(highlight_builder=highlights), "radiologist")
    for highlight in response.role_highlights:
        assert "contrast allergy" not in highlight.why_it_matters.lower()
        if "penicillin" in highlight.why_it_matters.lower():
            assert "contrast" not in highlight.why_it_matters.lower()
    assert any("Contrast reaction is not documented." == item for item in response.not_documented)
    assert "chest pain" in _event(response, response.role_highlights[0].event_id).description.lower()


def test_blood_pressure_does_not_gain_mmhg():
    """A vital recorded as 160/100 is returned as 160/100."""
    events = json.loads(json.dumps(CANONICAL_EVENTS))
    for row in events:
        if row["event_type"] == "vital":
            row["description"] = "Blood pressure 160/100 mmHg on 2026-03-12."
            row["title"] = "Blood pressure 160/100 mmHg"
    script = ScriptedCompletions(
        timeline_events=events,
        summary=SHARED_SUMMARY.replace("160/100", "160/100 mmHg"),
    )
    response = _run(script, "cardiologist")
    blob = json.dumps(response.model_dump())
    assert "mmHg" not in blob
    assert "mm Hg" not in blob
    assert "160/100" in blob


def test_missing_structured_facts_are_restored_before_summary_and_highlights():
    """An empty timeline model still leaves the chart facts for the next two steps."""
    script = ScriptedCompletions(timeline_events=[])
    response = _run(script, "nurse")
    _assert_shared_chart(response)
    summary_call = next(
        call for call in script.calls if "STEP: clinical_summary" in call["messages"][-1]["content"]
    )
    summary_prompt = summary_call["messages"][-1]["content"]
    assert "PATIENT_DATA_JSON" not in summary_prompt
    assert "0.8" in summary_prompt
    assert "160/100" in summary_prompt
    assert "Insulin" in summary_prompt
    assert "VIEWER_ROLE" not in summary_prompt


def test_highlight_without_an_event_id_is_not_kept_as_a_fact():
    """A citation that does not match the timeline is dropped, and a gap can move."""

    def highlights(role, events):
        payload = compliant_from(role, events)
        payload["role_highlights"].append(
            {
                "event_id": "evt-999",
                "why_it_matters": "ECG is not documented.",
                "salience": "lead",
            }
        )
        payload["role_highlights"].append(
            {
                "event_id": "evt-998",
                "why_it_matters": "The patient has a new diagnosis of infarction.",
                "salience": "lead",
            }
        )
        return payload

    response = _run(ScriptedCompletions(highlight_builder=highlights), "cardiologist")
    assert all(item.event_id != "evt-999" for item in response.role_highlights)
    assert all(item.event_id != "evt-998" for item in response.role_highlights)
    assert "infarction" not in json.dumps(response.model_dump()).lower()
    assert any("ECG is not documented." in item for item in response.not_documented)


def compliant_from(role, events):
    """Copy the compliant highlights so a test can edit one role."""
    from tests.fixtures.scripted_model import compliant_highlights

    return json.loads(json.dumps(compliant_highlights(role, events)))
