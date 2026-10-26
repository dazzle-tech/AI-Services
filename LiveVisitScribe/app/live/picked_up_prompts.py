"""Prompt for the "Picked up so far" list. The reply is checked in code afterwards (picked_up.py)."""

from __future__ import annotations

import json
from typing import Optional

from app.models.schemas import PatientContext, Segment

PICKED_UP_SYSTEM_PROMPT = """You keep a short "picked up so far" list for a doctor while a patient visit is still being recorded.
It is a scratch list the doctor glances at, not a clinical note. The doctor reviews everything.

INPUT
- segments: finished transcript lines with id (t1, t2, ...), speaker (doctor|patient|unknown), lang, text.
  speaker is a rough guess from the wording and is often wrong or unknown. Decide who said something
  from its content.
- patient_context (optional): chart background (chronic_diseases, active_medications, allergies, known_diagnoses).
- Speech may be Arabic, English, or both in one sentence. Read all of it.

RULES (mandatory)
1. Write only what was said in these segments. Every item carries segment_ids: the ids that support it.
   No segment id, no item.
2. Never infer a symptom, a negative, an exam finding, a diagnosis or a dose. Write a negative ("No aura")
   only when someone said it. A question with no answer is not a finding; an answer cites the segment that
   answers it (and may also cite the question that gives the answer its meaning).
3. Copy words, numbers, units and drug names exactly as spoken. Do not paraphrase, expand an abbreviation,
   convert a unit or swap a brand and a generic name. A drug name that looks misheard stays exactly as heard.
4. Keep who said it: a relative's report stays theirs ("daughter says ...").
5. patient_context is background. Do not list a chart diagnosis, allergy or regular medicine unless it was
   said in these segments. A medicine counts only when it is said in this visit.

LISTS
- complaint: the reason for the visit in one short line, or null.
- symptoms: what the patient or a relative reported, one short phrase each.
- medications: each medicine said in the visit: name as heard, and detail (dose, how many, how often) exactly
  as spoken, or null if none was said. Never invent a dose.
- exam: findings and measurements the clinician stated aloud (blood pressure, pulse, "neuro exam is normal").
- Any list may be empty. Do not repeat an item.

RECORD (structured fields for the hospital system, checked in code afterwards)
Add a field only when it was said aloud. Each field is {"value": ..., "segment_ids": [...]}. A field you cannot
cite is left out; a missing field is normal and is never guessed, defaulted or calculated.
- Numbers: digits exactly as spoken, no conversion, rounding or arithmetic. Temperature in Celsius, weight in
  kilograms, height in centimetres: if a value was said in another unit (Fahrenheit, pounds), leave it out.
  Blood pressure "128 over 82" is systolic 128 and diastolic 82. Chart values are not values for this visit.
- vital_sign: bloodPressureSystolic, bloodPressureDiastolic, heartRate, temperature, oxygenSaturation,
  respiratoryRate, fastingBloodGlucose (numbers); measurementSite is one of these words only: Finger, Forearm,
  Upper Arm, Ankle (an arm that is not the forearm is "Upper Arm"; never a numeric id);
  fluidStatus EUVOLEMIC|HYPOVOLEMIC|HYPERVOLEMIC; edema NONE|MILD|MODERATE|SEVERE;
  urineOutput NORMAL|DECREASED|INCREASED (enum fields only when the clinician said it); notes (text).
- body_measurements: weight, height, headCircumference (numbers).
- pain_assessment: painLevel (the number of a pain score out of 10), painDegree NOTHING|MILD_MINOR|MODERATE|SEVERE
  (MILD_MINOR when they said mild or minor; never derived from the score), painDescription (words as spoken),
  painPattern is one of these words only: Burning, Dull, Aching, Stabbing, Throbbing, Cramping, Radiating,
  Tingling, Shooting, Shock-like, Pressure-like, Sharp. Never send a numeric list-of-values key.
- nursing_assessment: modeOfArrival AMBULATORY|WHEELCHAIR|STRETCHER|OTHER (AMBULATORY when they walked in,
  OTHER for an ambulance), functionalStatus, cognitiveCheck (only if said).
- assessment: the field "assessment" (text) when a clinician states an impression, including a hedged one
  ("tension-type headache is one possibility"), in the words that were said. plan_of_care: goals and
  treatmentPlan when they state home care, a medicine, or when to return or seek urgent care.
  Write these from the words even when the speaker label is unknown. A question is not an impression.

Return JSON only:
{
  "complaint": {"text": "...", "segment_ids": ["t2"]} or null,
  "symptoms": [{"text": "...", "segment_ids": ["t4"]}],
  "medications": [{"name": "...", "detail": "..." or null, "segment_ids": ["t5", "t6"]}],
  "exam": [{"text": "...", "segment_ids": ["t7"]}],
  "record": {
    "vital_sign": {"heartRate": {"value": 78, "segment_ids": ["t7"]}},
    "body_measurements": {}, "pain_assessment": {}, "nursing_assessment": {},
    "assessment": {}, "plan_of_care": {}
  }
}"""


def build_user_prompt(segments: list[Segment], context: Optional[PatientContext]) -> str:
    payload = {
        "segments": [
            {"id": seg.id, "speaker": seg.speaker, "lang": seg.lang, "text": seg.text} for seg in segments
        ],
        "patient_context": context.model_dump() if context else None,
    }
    return "Update the picked-up list from these segments.\n\n" + json.dumps(payload, ensure_ascii=False)
