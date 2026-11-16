# Role-Aware Timeline Service

FastAPI service that reads one chart extract and returns three layers for one role:

1. `timeline` — the shared chronological history.
2. `clinical_summary` — one problem-oriented summary written only from those timeline events. Age and sex may be restated when they were supplied. The same chart produces the same summary for every role.
3. `role_highlights` — ordered items for `nurse`, `radiologist`, or `cardiologist`. Each item cites an `event_id`, says why it matters, and has salience `lead` or `context`.

`not_documented` lists role-relevant facts that were not in the input. `processing_metadata` includes the configured model name, timestamp, event count, and `viewer_role`.

The service calls OpenAI only, through `OPENAI_API_KEY`, `OPENAI_MODEL`, and `OPENAI_BASE_URL`. It does not choose a model of its own.

One request runs three model steps: build the timeline, write the summary from those events, then write the highlights from those events plus the role profile. The highlight step may say that something was not documented. It may not add any other fact that is absent from the timeline.

## Clinical rules

- Use only facts present in the input. Do not add a dose, unit, result, trend, or diagnosis.
- Age and sex may be restated in plain language when they are present.
- A single lab value stays a single value. One troponin does not become a rise, a fall, or an infarct unless a source note already says that.
- If two notes disagree, keep both and name both sources.
- Blood pressure recorded as `160/100` stays `160/100`. Do not add mmHg. Vitals have no unit.
- A missing fact is "not documented". Do not treat a gap as normal, and do not turn "not listed" into "the patient takes none."
- A highlight ranks and explains. It does not hide or delete timeline events.
- Every highlight cites an `event_id`. A point with no event belongs in `not_documented`.
- Do not place orders, choose a contrast protocol, or recommend a drug change.
- Medication fields are name, start date, optional end date, and optional status. Do not invent dose, route, or frequency.
- Model JSON is validated with Pydantic. Malformed JSON is retried and repaired. Temperature is sent low, and omitted when the model rejects it.

Structured facts the timeline model omits are added from the input before the summary and highlight steps. Those added events restate the input. They do not add an interpretation.

## Role profiles

**Nurse, read first:** why the patient is here, latest vitals and escalation symptoms, allergies, active high-risk medicines (insulin, anticoagulants, opioids, new starts and stops), and abnormal labs to report. Old procedures stay in the history unless the chart ties them to a current device, wound, or bleeding precaution. Name as not documented when absent: the rest of the vital set, glucose if insulin is active, dose, route, and frequency.

**Radiologist, read first:** the clinical question, diagnoses that change what to look for, prior procedures and devices, renal function, and any documented contrast reaction. Do not present a penicillin allergy as a contrast allergy. Do not add a metformin contrast warning unless the chart states reduced kidney function or a note says to hold it. Name as not documented when absent: the study ordered, creatinine or eGFR, contrast reaction, prior imaging report, and procedure findings.

**Cardiologist, read first:** the symptom timeline, cardiac biomarkers exactly as recorded, prior cardiac diagnoses and procedures, blood pressure, and cardiac or antithrombotic medicines that are actually listed. One elevated troponin is one elevated troponin. Name as not documented when absent: ECG, a second troponin, the reference range, antithrombotic therapy, and angiogram findings.

## Acceptance chart

58 years, male. Type 2 diabetes 2022-05-01. Hypertension 2021-03-10. Metformin from 2022-05-02, active. Insulin from 2023-11-18, active. Troponin 0.8 ng/mL, flagged high, 2026-03-13. Blood pressure 160/100 on 2026-03-12. Coronary angiography completed 2020-02-15. Admission 2026-03-12 for chest pain. Note the same day: admitted with chest pain and shortness of breath. Penicillin allergy recorded 2020-01-01.

On this chart:

- All three roles get the same `clinical_summary`.
- The nurse highlight leads with the symptoms, the blood pressure, the penicillin allergy, the active insulin, and the troponin value. It does not lead with the 2020 angiogram.
- The radiologist highlight leads with chest pain and shortness of breath, names renal function as not documented, and does not call penicillin a contrast allergy.
- The cardiologist highlight leads with the symptoms, the single troponin, and the prior angiogram. It does not describe the arteries or diagnose an infarct.

## Project structure

```text
RoleAwareTimelineService/
  main.py
  requirements.txt
  README.md
  Dockerfile
  docker-compose.yml
  .env.example
  pytest.ini
  postman/
  app/
    api/routes.py
    ai/client.py
    ai/prompts.py
    ai/guardrails.py
    core/config.py
    models/schemas.py
    services/timeline_service.py
    services/timeline_builder.py
  tests/
```

Pydantic models are the API contract and are published at `/openapi.json`. The Postman collection carries runnable requests, the acceptance chart, and structural assertions.

## Run locally

```bash
pip install -r requirements.txt
copy .env.example .env
```

Set `OPENAI_API_KEY`, `OPENAI_MODEL`, and `OPENAI_BASE_URL` in `.env`. Then:

```bash
python main.py
```

The API listens on `http://localhost:8040`. Interactive docs are at `http://localhost:8040/docs`.

## Docker

Copy `.env.example` to `.env`, set the OpenAI values, then:

```bash
docker compose up --build
```

The service is published on port `8040`. Compose does not start a local model.

## API

- `GET /`
- `GET /api/v1/health` — reports whether OpenAI settings are present. It does not call the model.
- `POST /api/v1/generate-role-timeline`

`viewer_role` is `nurse`, `radiologist`, or `cardiologist`.

### Example request

```json
{
  "request_id": "acceptance-nurse",
  "viewer_role": "nurse",
  "patient_data": {
    "patient_id": "pt-acceptance-58",
    "age": "58 years",
    "gender": "male",
    "diagnoses": [
      {"name": "Type 2 diabetes", "date": "2022-05-01"},
      {"name": "Hypertension", "date": "2021-03-10"}
    ],
    "medications": [
      {"name": "Metformin", "start_date": "2022-05-02", "status": "active"},
      {"name": "Insulin", "start_date": "2023-11-18", "status": "active"}
    ],
    "lab_results": [
      {"name": "Troponin", "value": "0.8", "unit": "ng/mL", "date": "2026-03-13", "flag": "high"}
    ],
    "vitals": [
      {"name": "Blood pressure", "value": "160/100", "date": "2026-03-12"}
    ],
    "procedures": [
      {"name": "Coronary angiography", "date": "2020-02-15", "status": "completed"}
    ],
    "encounters": [
      {"type": "admission", "date": "2026-03-12", "reason": "chest pain"}
    ],
    "notes": [
      {"date": "2026-03-12", "text": "Admitted with chest pain and shortness of breath."}
    ],
    "allergies": [
      {"name": "Penicillin", "date": "2020-01-01"}
    ]
  }
}
```

Event types are `diagnosis`, `medication`, `admission`, `procedure`, `lab`, `allergy`, `symptom`, and `vital`. Each event has `event_id`, `date`, `event_type`, `title`, `description`, `clinical_importance` (`high`, `medium`, or `low`), and `source`.

Validation errors return HTTP 422. A model failure after retry and repair returns HTTP 400.

## Tests

Unit tests mock the OpenAI client and cover this acceptance chart for all three roles. They do not call the live API.

```bash
pytest
```

## Postman

The collection is `postman/collections/RoleAwareTimelineService`. `base_url` defaults to `http://localhost:8040`. The OpenAI key stays in the service `.env` and is not a Postman variable.
