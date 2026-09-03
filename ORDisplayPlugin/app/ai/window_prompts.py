"""Per-window extraction prompt fragments."""

from typing import Any, Dict, Type

from pydantic import BaseModel

EXTRACTION_SYSTEM_PROMPT = """You extract structured clinical fields from a short operating-room dictation for one EMR window.

Rules:
- Extract only what is explicitly stated or clearly implied in the text. Never invent clinical values.
- Leave any field you cannot support from the text as null, and list its name in missing_fields.
- If existing_fields is provided, merge intelligently: keep prior non-null values unless the new text clearly updates them.
- Output strict JSON matching the given field schema, nothing else. No markdown.
- Preserve numbers and units exactly as spoken (e.g. "100 mg", "36.5 °C").
- Include _low_confidence_fields: an array of field names where the text was ambiguous.

JSON shape:
{
  "fields": { ... exactly the field names listed, values or null ... },
  "missing_fields": ["field_name", ...],
  "_low_confidence_fields": ["field_name", ...]
}
"""

WINDOW_FIELD_GUIDES: Dict[str, str] = {
    "nursing_verification_of_marking_site": """
Window: Nursing — Verification of Marking Site

Return exactly these two top-level keys under fields: checklist, siteMarking.

checklist: always an array of these four items, in this order. Keep key and label exact.
Set checked true/false only if the dictation clearly says so; otherwise checked=null.
Put extra spoken detail in note (empty string if none).

1. key=site_side_level_documented label="Site / Side / Level documented, if applicable"
2. key=pre_procedural_checklist_completed label="Pre-Procedural Check List Completed"
3. key=procedure_surgical_consent_completed label="The Procedure/Surgical Consent Completed"
4. key=anesthesia_consent_completed label="The Anesthesia Consent Completed, if applicable"

siteMarking:
- status must be one of:
  MARKED — site was marked (set marked=true). Put location/laterality in note.
  NOT_MARKED_SINGLE_ORGAN — not marked because it is a single organ (marked=false)
  NOT_MARKED_PREMATURE_INFANT_OR_TEETH — not marked because premature infant or teeth (marked=false)
  NOT_MARKED_PATIENT_REFUSED — patient refused marking (marked=false)
  NOT_STATED — marking was not mentioned (marked=null)
- Do not invent a status. If unmarked reason is unclear, use NOT_STATED.
""",
    "nursing_time_out": """
Window: Nursing — Time Out

Return exactly these two top-level keys: checklist, staff.

checklist: always these six items, in this order. Keep key and label exact.
Set checked true/false only if clearly stated; otherwise checked=null.
Put extra spoken detail in note (empty string if none). Do not invent staff IDs.

1. key=correct_patient label="Correct Patient"
2. key=correct_procedure label="Correct Procedure"
3. key=correct_site_and_side label="Correct Site and Side"
4. key=correct_patient_position label="Correct Patient Position"
5. key=verification_of_site_markings label="Verification of site markings"
6. key=availability_of_correct_implants_equipment label="Availability of correct implants / special equipment"

staff:
{
  "surgeon": { "staffId": string or null, "displayName": string or null },
  "nurse": { "staffId": string or null, "displayName": string or null }
}
Only fill staffId/displayName if spoken. Never invent IDs or names.
""",
    "nursing_intraoperative": """
Window: Nursing — Intraoperative

Return exactly these top-level keys (camelCase). Use null when not spoken.
Never invent names, times, sizes, or IDs.

operationStaff: date (YYYY-MM-DD), timeInToOperationRoom, timeOutFromOperationRoom, room,
scrubNurse1, scrubNurse2, circulateNurse1, surgeon, surgeonAssist1, anesthesiologist

anesthesia: { type } — uppercase enum if clear: GENERAL, SPINAL, EPIDURAL, REGIONAL, LOCAL, MAC

position: { position, note }
position uppercase if clear: SUPINE, PRONE, LATERAL, LITHOTOMY, BEACH_CHAIR, SITTING, TRENDELENBURG

skinPreparationAndIncision: { preparationSkinWith, incisionSite }
preparationSkinWith uppercase if clear: POVIDONE_IODINE, CHLORHEXIDINE, ALCOHOL, OTHER

foleyCatheter: { na, catheterSize (int), urineOutputCc (int), color }
Set na=true only if the speaker says Foley is N/A / not used.

tourniquet: { na, startTime, endTime, totalDurationMinutes (int), pressureMmHg (int), site }

diathermiaAndLaser: { na, electroSurgicalUnit, dispersiveElectrodeSite, electroRangeCutting,
electroRangeCoagulation, skinConditionBefore, skinConditionAfter, note }

laser: { na, pulseEnergy, frequency, stoneEffect, laserFiber, note }
If laser was not used / N/A, set na=true and leave the rest null.

drains: { na, entries: [ { type, numberOfDrains, location, size, otherLabel } ] }
type uppercase if clear: HEMOVAC, CHEST_TUBE, PENROSE, JACKSON_PRATT, OTHERS
For OTHERS put the spoken name in otherLabel.

specimens: { na, entries: [ { type, numberOfSamples, location, otherLabel, description } ] }
type uppercase if clear: PATHOLOGY, FROZEN_SECTION, CULTURE, REMOVED_ORGAN_DESCRIPTION, OTHERS
""",
    "nursing_sign_out": """
Window: Nursing — Sign Out

Return exactly one top-level key: checklist.

checklist: always these four items, in this order. Keep key and label exact.
Set checked true/false only if clearly stated; otherwise checked=null.
response is YES, NO, or null — only when clearly stated for yes/no items.
Put extra spoken detail in note (empty string if none).

1. key=name_of_surgical_invasive_procedure label="Name of surgical/invasive procedure" response=null
2. key=instruments_sponge_needle_counts_completed label="Completion of instruments, sponge and needle counts"
3. key=labeling_of_specimens label="Labeling of specimens, if present labels are read aloud"
4. key=address_any_equipment_problems label="Address any equipment problems"
""",
    "anesthesia_pre_evaluation_plan": """
Window: Anesthesia Record — Pre-Anesthesia Evaluation Record & Anesthesia Plan

Return exactly these top-level keys (camelCase). Use null when not spoken; use empty string for
unmentioned free-text sub-fields inside pastMedicalHistory, clinicalExamination, airwayAssessment,
and clinicalData.

socialHistory: { allergies, smoker, alcoholic, substanceUse }
lastMeal: { food, foodDate (YYYY-MM-DD), fluid, fluidDate (YYYY-MM-DD) }
previousAnesthesiaAndSurgery: { previousAnesthesia, previousSurgery, difficultIntubation, complication, comments }
pastMedicalHistory: { cardiovascular, respiratory, neurological, urological, musculoskeletal, psychiatric,
  pregnancies, renalDisease, endocrine, hepatic, gastrointestinal, bloodVessel, otherDiseases }
vitalSigns: { weightKg, bpSystolic, bpDiastolic, pulseRate, tempC, spo2 }
clinicalExamination: { cardiovascular, respiratory, skin, sensors, neuromuscular, gcs, others }
airwayAssessment: { openMouth, thyromentalDistance, neckMobility, others }
clinicalData: { chestXray, ecg, others }
asa: { asaClass (e.g. "ASA II"), emergency (boolean) }
preAnesthesiaOrders: { orders }
preMedication: { preMedication, prophylacticAntibiotic ("YES"/"NO"), prophylacticAntibioticNote }
""",
    "anesthesia_induction_intraoperative": """
Window: Anesthesia Record — Induction Assessment and Intraoperative Anesthesia

Return exactly these top-level keys (camelCase). Use null when not spoken.

preInductionAssessment: {
  bpSystolic, bpDiastolic, hr, rr, o2Sat,
  npo ("YES"/"NO"), npoDate (YYYY-MM-DD),
  preMedication ("YES"/"NO"), preMedicationNote,
  date (YYYY-MM-DD)
}
intraoperativeAnesthesia: {
  induction, intubation, airway, position,
  anesthesiologistResident, anesthesiaTechnician
}
""",
    "anesthesia_observation_drugs": """
Window: Anesthesia Record — Patient observation and Drugs

Return exactly these top-level keys (camelCase). Use null when not spoken; use empty string for
unmentioned text sub-fields inside vitalSign and bloodLoss.

vitalSign: {
  bpSystolic, bpDiastolic, hr, oxygenSupply, etco2, spo2, tempC, tidalVolume, rr,
  act, fio2, rbs, o2Air
}
bloodLoss: { bloodQuantity, bloodLoss (integer ml) }
""",
    "operative_note": """
Window: Operative Note

Return exactly these top-level keys (camelCase). Use null when not spoken.

operativeDetails: { time (HH:MM), typeOfAnesthesia }
operationStaff: { mainSurgeon, surgeonsAssistant, surgicalStartTime (ISO-8601), surgicalEndTime (ISO-8601) }
operationNote: free-text narrative of the procedure
complication: string (e.g. "None")
estimatedBloodLossMl: integer milliliters
""",
}


def build_extraction_prompt(
    window_id: str,
    schema: Type[BaseModel],
    text: str,
    existing_fields: Dict[str, Any] | None,
) -> str:
    field_names = list(schema.model_fields.keys())
    guide = WINDOW_FIELD_GUIDES.get(window_id, "")
    existing = existing_fields if existing_fields else {}
    return (
        f"{guide.strip()}\n\n"
        f"Field names (use exactly these keys under 'fields'): {field_names}\n\n"
        f"Dictation text:\n{text}\n\n"
        f"existing_fields (may be empty):\n{existing}\n"
    )
