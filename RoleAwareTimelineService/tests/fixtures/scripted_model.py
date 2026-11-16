"""In-process stand-in for the OpenAI chat client. Tests never call the network."""
import json
import re
from types import SimpleNamespace

from tests.fixtures.acceptance_chart import CANONICAL_EVENTS, SHARED_SUMMARY


def completion(payload):
    """Build the small slice of a chat completion the client reads."""
    content = payload if isinstance(payload, str) else json.dumps(payload)
    message = SimpleNamespace(content=content)
    choice = SimpleNamespace(message=message)
    usage = SimpleNamespace(prompt_tokens=3, completion_tokens=5, total_tokens=8)
    return SimpleNamespace(choices=[choice], usage=usage)


def extract_json_after(text, label):
    """Read the JSON value that follows a prompt label."""
    marker = f"{label}:\n"
    start = text.index(marker) + len(marker)
    payload, _ = json.JSONDecoder().raw_decode(text[start:])
    return payload


def _event_id(events, predicate):
    for event in events:
        if predicate(event):
            return event["event_id"]
    raise AssertionError("Scripted model could not find an event the chart should contain")


def compliant_highlights(role, events):
    """Role highlights a compliant model returns for the acceptance chart."""
    symptom = _event_id(
        events,
        lambda event: event["event_type"] == "symptom" and "shortness of breath" in event["description"].lower(),
    )
    blood_pressure = _event_id(
        events,
        lambda event: event["event_type"] == "vital" and "160/100" in event["description"],
    )
    allergy = _event_id(
        events,
        lambda event: event["event_type"] == "allergy" and "penicillin" in event["title"].lower(),
    )
    insulin = _event_id(
        events,
        lambda event: event["event_type"] == "medication" and "insulin" in event["title"].lower(),
    )
    troponin = _event_id(
        events,
        lambda event: event["event_type"] == "lab" and "troponin" in event["title"].lower(),
    )
    angiogram = _event_id(
        events,
        lambda event: event["event_type"] == "procedure" and "angiograph" in event["title"].lower(),
    )
    admission = _event_id(events, lambda event: event["event_type"] == "admission")
    metformin = _event_id(
        events,
        lambda event: event["event_type"] == "medication" and "metformin" in event["title"].lower(),
    )

    if role == "nurse":
        highlights = [
            {
                "event_id": symptom,
                "why_it_matters": "The patient is here for chest pain and shortness of breath.",
                "salience": "lead",
            },
            {
                "event_id": blood_pressure,
                "why_it_matters": "Latest blood pressure is 160/100.",
                "salience": "lead",
            },
            {
                "event_id": allergy,
                "why_it_matters": "Penicillin allergy is recorded.",
                "salience": "lead",
            },
            {
                "event_id": insulin,
                "why_it_matters": "Insulin is an active high-risk medicine.",
                "salience": "lead",
            },
            {
                "event_id": troponin,
                "why_it_matters": "Troponin is 0.8 ng/mL, flagged high, on 2026-03-13.",
                "salience": "lead",
            },
            {
                "event_id": admission,
                "why_it_matters": "Admission on 2026-03-12 was for chest pain.",
                "salience": "context",
            },
            {
                "event_id": metformin,
                "why_it_matters": "Metformin remains active.",
                "salience": "context",
            },
            {
                "event_id": angiogram,
                "why_it_matters": "Coronary angiography was completed in 2020 and stays in the history.",
                "salience": "context",
            },
        ]
    elif role == "radiologist":
        highlights = [
            {
                "event_id": symptom,
                "why_it_matters": "Documented symptoms are chest pain and shortness of breath.",
                "salience": "lead",
            },
            {
                "event_id": angiogram,
                "why_it_matters": "Coronary angiography was completed on 2020-02-15.",
                "salience": "lead",
            },
            {
                "event_id": allergy,
                "why_it_matters": "Penicillin allergy is recorded.",
                "salience": "context",
            },
        ]
    elif role == "cardiologist":
        highlights = [
            {
                "event_id": symptom,
                "why_it_matters": "Symptom timeline: chest pain and shortness of breath on 2026-03-12.",
                "salience": "lead",
            },
            {
                "event_id": troponin,
                "why_it_matters": "One troponin result is recorded: 0.8 ng/mL, flagged high, on 2026-03-13.",
                "salience": "lead",
            },
            {
                "event_id": angiogram,
                "why_it_matters": "Coronary angiography was completed on 2020-02-15.",
                "salience": "lead",
            },
            {
                "event_id": blood_pressure,
                "why_it_matters": "Blood pressure 160/100 was recorded on 2026-03-12.",
                "salience": "context",
            },
        ]
    else:
        raise AssertionError(f"Unexpected role {role}")
    return {"role_highlights": highlights, "not_documented": []}


class ScriptedCompletions:
    """Replace chat.completions.create for one service instance."""

    def __init__(self, timeline_events=None, summary=SHARED_SUMMARY, highlight_builder=None):
        self.calls = []
        self.timeline_events = CANONICAL_EVENTS if timeline_events is None else timeline_events
        self.summary = summary
        self.highlight_builder = highlight_builder or compliant_highlights

    def __call__(self, **kwargs):
        messages = kwargs["messages"]
        user = messages[-1]["content"]
        self.calls.append({"messages": messages, "kwargs": kwargs})
        if "STEP: timeline" in user:
            return completion({"events": self.timeline_events})
        if "STEP: clinical_summary" in user:
            if "VIEWER_ROLE" in user:
                return completion({"clinical_summary": "Summary written for a viewer."})
            return completion({"clinical_summary": self.summary})
        if "STEP: role_highlights" in user:
            role = re.search(r"VIEWER_ROLE:\s*(\w+)", user).group(1)
            events = extract_json_after(user, "TIMELINE_JSON")
            return completion(self.highlight_builder(role, events))
        raise AssertionError(f"Unexpected model prompt: {user[:240]}")


def step_names(script):
    """Return the generation step of each mocked call."""
    names = []
    for call in script.calls:
        user = call["messages"][-1]["content"]
        if "STEP: timeline" in user:
            names.append("timeline")
        elif "STEP: clinical_summary" in user:
            names.append("summary")
        elif "STEP: role_highlights" in user:
            names.append("highlights")
        else:
            names.append("other")
    return names
