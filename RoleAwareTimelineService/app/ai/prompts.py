"""Prompt templates for the three generation steps."""
import json
from typing import Any, Dict, List, Optional, Sequence

ROLE_PROFILES: Dict[str, str] = {
    "nurse": """Nurse, read first:
- Why the patient is here.
- Latest vitals and escalation symptoms.
- Allergies.
- Active high-risk medicines: insulin, anticoagulants, opioids, and new starts and stops.
- Abnormal labs to report.
Leave old procedures in the history unless the chart ties them to a current device, wound, or bleeding precaution.
When these facts are absent, name them in not_documented: the rest of the vital set, glucose if insulin is active, dose, route, and frequency.
A highlight ranks and explains. It does not hide timeline events and it does not place orders or change a drug.""",
    "radiologist": """Radiologist, read first:
- The clinical question.
- Diagnoses that change what to look for.
- Prior procedures and devices.
- Renal function.
- Any documented contrast reaction.
Do not present a penicillin allergy as a contrast allergy.
Do not add a metformin contrast warning unless the chart states reduced kidney function or a note says to hold metformin.
When these facts are absent, name them in not_documented: the study ordered, creatinine or eGFR, contrast reaction, prior imaging report, and procedure findings.
Do not choose a contrast protocol.""",
    "cardiologist": """Cardiologist, read first:
- The symptom timeline.
- Cardiac biomarkers exactly as recorded.
- Prior cardiac diagnoses and procedures.
- Blood pressure.
- Cardiac or antithrombotic medicines that are actually listed.
One elevated troponin is one elevated troponin. Do not describe a rise, a fall, an infarct, or the arteries unless a timeline event already says that.
When these facts are absent, name them in not_documented: ECG, a second troponin, the reference range, antithrombotic therapy, and angiogram findings.
Do not recommend a drug change.""",
}


def _dump(payload: Any) -> str:
    """Serialize prompt JSON without changing characters."""
    return json.dumps(payload, indent=2, ensure_ascii=True)


def build_timeline_prompt(patient_data: Dict[str, Any]) -> List[Dict[str, str]]:
    """Build the timeline step. The viewer role is intentionally absent."""
    system = """You are a clinical timeline extraction model. STEP 1 builds the shared chronological history.

Use only facts present in PATIENT_DATA_JSON. Do not add a dose, route, frequency, unit, result, trend, or diagnosis.
Age and sex may be omitted from the timeline. They are not events.
A single lab value stays a single value. "Troponin 0.8 ng/mL, flagged high, on 2026-03-13" must not become a rise, a fall, or an infarct unless a source note already says that.
Blood pressure recorded as 160/100 stays 160/100. Do not add mmHg.
If two notes disagree, keep both events and name both sources in the descriptions.
A missing fact is not an event. Do not treat a gap as normal, and do not turn "not listed" into "the patient takes none."
Do not place orders, choose a contrast protocol, or recommend a drug change.
Merge obvious duplicates. Sort by date ascending.

Return a JSON object with this shape and no markdown:
{
  "events": [
    {
      "date": "source date",
      "event_type": "diagnosis | medication | admission | procedure | lab | allergy | symptom | vital",
      "title": "short factual title",
      "description": "factual description using only the input",
      "clinical_importance": "high | medium | low",
      "source": "diagnoses | medications | lab_results | vitals | procedures | encounters | notes | allergies"
    }
  ]
}

Event selection:
- Diagnoses, medication starts, stops, and current statuses, admissions, procedures, labs, allergies, vitals, and symptoms stated in notes or encounter reasons.
- Use admission for an admission encounter.
- Use symptom for symptoms stated in a note.
- Use vital for vital signs. Do not invent a unit.
- Use medication for medicines that are listed. Do not invent dose, route, or frequency.
- Use the input field name as source. Do not use the field name as event_type.
- Preserve names, values, flags, statuses, and dates exactly."""
    user = f"""STEP: timeline
PATIENT_DATA_JSON:
{_dump(patient_data)}

Extract the shared timeline. Return only the JSON object."""
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def build_summary_prompt(
    events: Sequence[Dict[str, Any]],
    age: Optional[str],
    gender: Optional[str],
) -> List[Dict[str, str]]:
    """Build the summary step from timeline events plus age and sex only."""
    allowed = {"age": age, "gender": gender}
    system = """You write one problem-oriented clinical summary from a timeline that was already extracted.

Use only TIMELINE_JSON. Age and sex in AGE_AND_SEX_JSON may be restated in plain language when the value is not null. Nothing else may be added.
Do not address a viewer. Do not mention who will read the summary.
This is a clinical summary, not a status sentence. Do not say that generation succeeded.
A single lab value stays a single value. Do not invent a rise, a fall, a trend, or a diagnosis.
Do not add mmHg, a dose, a route, or a frequency.
If two events disagree, keep both and name both sources.
A missing fact stays missing. Do not call a gap normal, and do not write that the patient takes none of an unlisted medicine.

Return a JSON object and no markdown:
{"clinical_summary": "problem-oriented summary"}"""
    user = f"""STEP: clinical_summary
AGE_AND_SEX_JSON:
{_dump(allowed)}
TIMELINE_JSON:
{_dump(list(events))}

Write the clinical summary from these events only. Return only the JSON object."""
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def build_highlight_prompt(
    events: Sequence[Dict[str, Any]],
    viewer_role: str,
) -> List[Dict[str, str]]:
    """Build the highlight step from timeline events and one role profile."""
    profile = ROLE_PROFILES[viewer_role]
    system = """You rank timeline events for one clinical role. STEP 3 may explain events. It may not add facts.

Use only TIMELINE_JSON and the role profile. You may say that a role-relevant fact was not documented. Do not introduce any other fact that is absent from the timeline.
Every role_highlights item cites an event_id from TIMELINE_JSON. If a point has no event_id, put it in not_documented instead of the highlight list.
salience is "lead" for what this role reads first and "context" for the rest of the history.
A highlight ranks and explains. It does not hide or delete timeline events.
Do not place orders, choose a contrast protocol, or recommend a drug change.
Do not add a dose, route, frequency, unit, trend, or diagnosis.
Blood pressure stays the recorded value. Do not add mmHg.
One lab value stays one lab value.
Do not present a penicillin allergy as a contrast allergy.
Do not describe arteries or diagnose an infarct unless the cited event already says that.

Return a JSON object and no markdown:
{
  "role_highlights": [
    {"event_id": "evt-001", "why_it_matters": "why this event matters for this role", "salience": "lead"}
  ],
  "not_documented": ["fact that was not in the timeline"]
}"""
    user = f"""STEP: role_highlights
VIEWER_ROLE: {viewer_role}
ROLE_PROFILE:
{profile}
TIMELINE_JSON:
{_dump(list(events))}

Write the highlights for this role. Return only the JSON object."""
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]
