# ConvoVoiceAgent

Single call for a doctor–patient recording. The client talks only to this service.

1. Sends the audio to **ConvoScribe** (`POST /api/v1/analyze`) for transcript, speaker roles, and the clinical note.
2. Sends that note to **SystemDisplayPlugin** (`POST /api/v1/reshape`) to fill the requested views.
3. Returns DisplayPlugin’s JSON as the response.

API: http://localhost:8036  
Docs: http://localhost:8036/docs

`python main.py` starts ConvoScribe on **8026** and SystemDisplayPlugin on **8031** when those ports are not already up. Their code is unchanged under `services/`. A service that is already running is left as it is, and it is not stopped when the agent exits.

## Local development

```bash
cd ConvoVoiceAgent
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env

python main.py
```

## Example

Multipart audio:

```bash
curl -X POST http://localhost:8036/api/v1/analyze ^
  -F "audio=@visit.wav" ^
  -F "context_type=appointment" ^
  -F "purpose=soap_note" ^
  -F "view_ids=soap_note"
```

JSON base64:

```bash
curl -X POST http://localhost:8036/api/v1/analyze ^
  -H "Content-Type: application/json" ^
  -d "{\"audio_base64\":\"...\",\"filename\":\"visit.wav\",\"view_ids\":[\"soap_note\"]}"
```

Optional fields: `context_type` (default `appointment`), `purpose` (default `soap_note`), `detail_level` (default `standard`), `view_ids` (default `soap_note`). Multipart `view_ids` may be comma-separated or a JSON array.

The response is the display result:

```json
{
  "results": [
    {
      "view_id": "soap_note",
      "data": {
        "ChiefComplaint": "Headache",
        "Assessments": "Tension headache."
      },
      "warnings": []
    }
  ]
}
```

There is one summary model call per request, in ConvoScribe. Its `soap_note` output carries the SOAP fields plus `chart` (the 12 `soap_note` field strings), `vitals` and `measurements`. SystemDisplayPlugin's seeded views copy those values with `direct` transforms and make no model call. If an older ConvoScribe response has no `chart`, this service builds one from `subjective`, `objective`, `assessment` and `plan` (+ `follow_up`), with "Not discussed" left empty. A narrative summary or clinical document is flattened onto the same fields first.

## Ambient draft

Two more request/response endpoints build a sourced visit draft for the physician to review. This service stores nothing: no audio, drafts, or reviews. Asklepios owns the visit (consent, recording, pause/resume, audio storage, retention, review, accept/reject, sign, order validation, audit, metrics, feature flags, kill switch).

Both endpoints accept `X-API-Key` and `X-Clinician-Id` when present and forward them to ConvoScribe. They do not authorize against a visit, and missing headers are allowed.

### `POST /api/v1/draft`

Multipart `audio` file, or JSON with `audio_base64` and optional `filename`. Optional fields:

| Field | Values | Default |
|-------|--------|---------|
| `note_language` | `english`, `arabic` | `english` |
| `instruction_language` | patient’s language | `note_language` |
| `specialty` | `general_practice`, `internal_medicine`, `pediatrics`, `obgyn` | `general_practice` |
| `note_length` | `brief`, `standard`, `detailed` | `standard` |
| `note_form` | `bullets`, `prose` | `prose` |
| `patient_context` | `{chronic_diseases, active_medications, allergies, last_visit}` (multipart: JSON string) | none |
| `suggest_icd10` | `true`, `false` | `true` |
| `suggest_orders` | `true`, `false` | `true` |

```bash
curl -X POST http://localhost:8036/api/v1/draft ^
  -H "X-Clinician-Id: dr-smith" ^
  -F "audio=@visit.wav" ^
  -F "specialty=pediatrics" ^
  -F "note_language=arabic" ^
  -F "patient_context={\"allergies\":[\"penicillin\"]}"
```

Flow: one ConvoScribe `POST /api/v1/analyze` call with `purpose=transcript_only` (transcript and speaker roles, no ConvoScribe summary), then the note model as the only summary step, then SystemDisplayPlugin `POST /api/v1/reshape` with an inline `soap_note` decoder of `direct` fields, so the reshape copies the sourced text and does not rewrite it.

Response:

- `transcript`: `[{id, speaker, lang, start_ms, end_ms, text, confidence}]`. Ids `s1..sN` are assigned here from ConvoScribe segments, and `speaker` comes from the role map. `lang` is `en`, `ar`, `mixed`, or `unknown`.
- `sections`: `chief_complaint`, `hpi`, `review_of_systems`, `physical_exam`, `assessment_plan`, each `{sentences: [{sentence_id, text, segment_ids, low_confidence}]}`. `assessment_plan` sentences also carry `part` (`assessment` or `plan`) and start with the diagnosis they belong to.
- `soap_note`: SystemDisplayPlugin field names (`ChiefComplaint`, `HPI`, `MedicalHistory`, `SurgicalHistory`, `FamilyAndSocialHistory`, `OtherSubjective`, `Vitals`, `PhysicalExamination`, `Assessments`, `DiagnosticImagesAndTests`, `Procedures`, `TreatmentPlans`). Review of systems is a labelled block inside `PhysicalExamination`, spoken vitals and measurements go to `Vitals`, assessment sentences go to `Assessments`, and plan sentences go to `TreatmentPlans`. Fields no section fills are `null`.
- `diagnoses`: `[{id, icd10, label, rank, suspected, chronic, segment_ids}]`. Empty when `suggest_icd10` is `false`. The assessment text is still written either way.
- `orders`: `[{id, kind, payload, segment_ids}]`, suggestions only. Empty when `suggest_orders` is `false`. The plan text is still written either way. `follow_up` has `payload.date` and `booked: false`. `sick_leave` has `start_date`, `end_date`, and `confirm_required: true`. Validation (Medication & Test Order Validation, port 8006) happens in Asklepios on accept.
- `mentions`: `[{kind: allergy|warning|sick_leave, text, segment_ids, confirm_required: true}]`.
- `instructions`: `{language, text, segment_ids}` in `instruction_language`.
- `flags`: `[{kind: drug_name|dose, text, segment_ids}]` for drug names and doses spoken in low-confidence segments.
- `possible_transcription_errors`: `[{heard, likely, segment_ids}]` for phrases that look misheard (for example `heard: "less than a pearl 10 mg"`, `likely: "lisinopril 10 mg"`). The note keeps the transcript wording; only the physician applies a correction. A hint is dropped unless `heard` appears in a cited segment.
- `patient_context_used`: `false` when `patient_context` is omitted or empty.
- `elapsed_ms`: time from request start to response.

### `POST /api/v1/sections/regenerate`

JSON: `transcript` (the array from `/draft`), `section` (one of the five names), `instruction` (free text such as `"shorter"` or `"add smoking history"`), plus the same `note_language`, `specialty`, `note_length`, `note_form`, and optional `patient_context`.

Response: `{section, sentences, soap_note, diagnoses, orders, mentions, instructions, flags, possible_transcription_errors, patient_context_used}`, with the same shapes and evidence rules as `/draft`. `diagnoses` (with ICD-10 suggestions), `orders`, `mentions` and `instructions` are filled only when `section` is `assessment_plan`; for other sections they are empty and `instructions` is `null`. `flags` and `possible_transcription_errors` only cover segments the regenerated section cites. `soap_note` contains only the fields that section fills. `review_of_systems` and `physical_exam` both fill `PhysicalExamination` and each returns only its own part, so the caller combines them. `physical_exam` also fills `Vitals`, and `hpi` also fills `MedicalHistory`. `assessment_plan` fills `Assessments` and `TreatmentPlans`.

### Evidence rules

The system prompt is in `app/ai/ambient_prompts.py`, with specialty addenda for the four specialties (same JSON schema for all). Whatever the model returns, `app/services/ambient_draft.py` applies these before anything is returned:

- A sentence, diagnosis, order, mention, flag, or instructions block that cites no segment id in this transcript is dropped. So is one whose cited segments are all questions ("Any vision changes?"): a question is not evidence for a finding or a negative.
- A spoken finding the model left out is added back in the words that were said: an exam finding such as "alert and neurologically normal" or "no fever on my touch", and a dictated "patient reports ..." line. A greeting, a question, or "I will record your vitals" is not added. A line already in the note or the instructions is not added again. "one side" and "1 side" are the same line, so it is not written twice.
- A spoken measurement the model left out of `record` is filled from the transcript when the number is in range. Head circumference 55 centimetres stays 55.
- A negative, or a review-of-systems word, the speaker did not say is removed. "Any vision changes?" with no answer is not "no vision changes", and "light bothers me" is not rewritten as "light sensitivity". "No nausea" stays when the patient said it.
- A medication `route` that is really a frequency ("as needed", "twice daily") is moved to `frequency`.
- If the note text contains the `likely` wording of a `possible_transcription_errors` hint for the same segment, it is put back to the `heard` wording. Only the physician applies the correction.
- In `soap_note`, `Assessments` and `TreatmentPlans` print each diagnosis heading once, with its sentences under it. Exam sentences starting `Vitals:` or `Measurements:` go to `Vitals` instead of `PhysicalExamination`, and HPI sentences starting `History:` go to `MedicalHistory`.
- Sentences citing a segment below `AMBIENT_LOW_CONFIDENCE_THRESHOLD` get `low_confidence: true`. Drug names and doses in those segments are flagged.
- ICD-10 codes are checked against `app/clinical/icd10_codes.json` (a small ICD-10-CM table). A code not in the table is removed and the diagnosis keeps its label with `icd10: null`.
- Mentions always have `confirm_required: true`.

The prompt also tells the model not to infer exam findings, diagnoses, or negative review of systems, to keep spoken hedges, to copy drug names, doses and numbers as spoken, and to treat `patient_context` as background, not new findings. Its MEDICAL TERMINOLOGY block (also in ConvoScribe's summary prompt and SystemDisplayPlugin's mapping prompt) forbids paraphrasing medical terms, expanding abbreviations, converting units, swapping brand and generic names, silently correcting a misheard term, treating an unanswered question as a negative, and dropping who reported a fact.

Segment confidence is read from ConvoScribe segment `confidence` (0–1) or `avg_logprob` when present. ConvoScribe’s current `/analyze` response does not include either, so until it does, `low_confidence` stays `false` and `flags` stays empty for real recordings.

### Asklepios record (`record` in `/draft`)

`/draft` also returns the visit in the shapes Asklepios posts. `patientId` and `encounterId` are always `null`: this service does not take them.

| `record` key | Payload | Where the values come from |
|---|---|---|
| `vital_sign` | blood pressure systolic/diastolic, `heartRate`, `temperature`, `oxygenSaturation`, `respiratoryRate`, `fastingBloodGlucose` (string), `measurementSite`, `fluidStatus`, `edema`, `urineOutput`, `notes`; `isTriage: false`, `isActive: true` | model, only values said aloud |
| `body_measurements` | `weight`, `height`, `headCircumference`; `isActive: true` | model, only values said aloud |
| `pain_assessment` | `painDegree`, `painDescription`, `painPattern`, `painLevel` (`LEVEL_0`..`LEVEL_10`), `painAssessmentType` | model; `painAssessmentType` is `NUMERIC` when a score was said; `painDegree` is never derived from the score |
| `nursing_assessment` | `reasonOfVisit`, `modeOfArrival`, `functionalStatus`, `cognitiveCheck`, `patientConditions`, ... | `reasonOfVisit` is the chief complaint; `patientConditions` is `patient_context.chronic_diseases` joined by `, `; `byPatient: true`, `sourceOfInformation: null`, `priorityLevel: "NORMAL"`, `isActive: true` are the form defaults (change them in the UI); `bloodGroup` stays `null` (patient record) |
| `clinical_visit` | `chiefComplaint`, `historyOfPresentIllness`, `physicalExaminationSummery` | the same sentences as `soap_note` (review of systems is part of the exam summary, `History:` lines are appended to the HPI). Each key is its own request body in Asklepios |
| `patient_diagnosis` | list: `diagnosisId`, `type` (`PRIMARY`/`SECONDARY`), `suspected`, `major` | one item per entry of `diagnoses`, same order. `diagnosisId` is `null`: this service has no catalog, so resolve it from `diagnoses[i].icd10`. `major` is `true` for the primary diagnosis |
| `assessment` | `assessment` | `assessment` sentences |
| `plan_of_care` | `goals`, `treatmentPlan` | `goals` only if the doctor stated a goal; `treatmentPlan` from `plan` sentences |

Also in the response:

- `record_status`: `empty`, `partial` or `complete` per group. An `empty` group is `null` in `record`: do not post it.
- `missing_required`: for a `partial` group, the required fields nobody said (vitals: the six required readings; body measurements: weight and height; pain: `painDegree`; nursing: `reasonOfVisit`). Ask the clinician for them before posting; the service never fills them in.
- `record_evidence`: `"group.field"` (or `"patient_diagnosis.0"`) to the transcript segment ids it came from.

Checks in code (`app/clinical/asklepios.py`) on top of the prompt: a field must cite an existing, non-question segment; a number must be said in a cited segment (no conversion, except height in metres to centimetres) and be plausible (for example heart rate 20-300, SpO2 50-100, temperature 25-45 Celsius, so a Fahrenheit reading is dropped); systolic must be above diastolic or both are dropped; an enum or list-of-values field must be one Asklepios stores, and its cited segment must say it. List-of-values fields are the label word, never the numeric key: `measurementSite` is Finger, Forearm, Upper Arm, or Ankle; `painPattern` is Burning, Dull, Aching, Stabbing, Throbbing, Cramping, Radiating, Tingling, Shooting, Shock-like, Pressure-like, or Sharp. `painDegree` is NOTHING, MILD_MINOR, MODERATE, or SEVERE. `modeOfArrival` is AMBULATORY, WHEELCHAIR, STRETCHER, or OTHER. Free text may not contain a number that was not said.

`/sections/regenerate` returns `record` and `record_evidence` too, with only the keys that section decides (for example `hpi` gives `clinical_visit.historyOfPresentIllness`, `assessment_plan` gives `assessment`, `plan_of_care.treatmentPlan` and `patient_diagnosis`), so the caller never overwrites a field the section does not cover. Vitals, measurements and pain come only from `/draft`.

### Note model

`AMBIENT_NOTE_MODEL` on any OpenAI-compatible endpoint (`OPENAI_BASE_URL`, `OPENAI_API_KEY`), so switching models is a config change. Speech stays on ConvoScribe’s `TRANSCRIPTION_BACKEND`, which defaults to `gpt_transcribe` and transcribes the uploaded file. `TRANSCRIPTION_BACKEND=stub` is for tests: it ignores the audio and returns one sample visit for every file. `USE_LLM_STUB=true` builds a deterministic draft from the transcript by keyword rules with no network. It copies segment text verbatim and does not translate. Without a key and with the stub off, `/draft` returns 503.

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `API_PORT` | `8036` | Server port |
| `CONVOSCRIBE_BASE_URL` | `http://localhost:8026` | Transcript and clinical note |
| `SYSTEM_DISPLAY_BASE_URL` | `http://localhost:8031` | View mapping |
| `HTTP_TIMEOUT_SECONDS` | `180` | Outbound timeout for both calls |
| `DEFAULT_VIEW_IDS` | `soap_note` | Views used when the request omits `view_ids` |
| `AMBIENT_NOTE_MODEL` | `gpt-4o` | Model for the ambient draft |
| `OPENAI_API_KEY` | empty | Key for the note model |
| `OPENAI_BASE_URL` | empty | OpenAI-compatible endpoint; empty uses api.openai.com |
| `OPENAI_TEMPERATURE` | `0.1` | Note model temperature |
| `OPENAI_TIMEOUT_SECONDS` | `120` | Note model timeout |
| `USE_LLM_STUB` | `false` | Deterministic offline draft |
| `AMBIENT_LOW_CONFIDENCE_THRESHOLD` | `0.6` | Segment confidence below this is low confidence |

## Postman

`postman/ConvoVoiceAgent.postman_collection.json` has a request for every endpoint, with saved example responses (success and common errors) based on `services/ConvoScribe/samples/visit_3min_sample.wav`. Multipart requests upload that file; reselect it in Postman if your checkout path differs. Running a Draft request saves its transcript to `{{draftTranscript}}` for **Regenerate — from last draft**.

## Testing

```bash
pytest
```
