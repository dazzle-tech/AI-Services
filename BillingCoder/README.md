# CodingAssist

AI auto-coding & charge-capture service. Takes raw clinical documentation (op notes, progress notes, ED notes) from one encounter and returns a compliance-enforced, structured charge ticket with ontology-grounded ICD-10-CM/CPT/HCPCS codes.

> Sibling project: [RadiologyReporter](../RAdiology/) generates structured radiology reports. Its output can be passed into this service via `upstream_entities` to skip re-extraction of already-grounded findings — see the chaining example below.

## What it does

The service runs a 6-phase pipeline on every request:

1. **Hydrate** — read the request body (encounter metadata, one or more source documents, optional upstream entities).
2. **Normalize** — LLM call #1 reconciles multiple source documents into one narrative, preferring more definitive/later-stage sources (e.g. a pathology report over a surgeon's intra-operative impression). Document text is treated strictly as data — embedded instruction-like text is quoted and flagged, never obeyed.
3. **Extract + Ground** — LLM call #2 identifies diagnoses (with `confirmed`/`suspected`/`ruled_out` status) and procedures; the service resolves each to ICD-10-CM or CPT/HCPCS via a local RAG cache, falling back to the live NLM Clinical Tables API on a cache miss for ICD-10-CM and HCPCS. **CPT has no free public lookup API** (AMA copyright), so CPT grounding is RAG/seed-only — see `coding_seed_terms.json`.
4. **Compliance check** — deterministic checks against NCCI procedure-to-procedure (PTP) bundling edits, Medically Unlikely Edit (MUE) per-code unit ceilings, LCD-style medical-necessity covered-indications, and ruled-out diagnoses.
5. **Draft** — LLM call #3 writes the structured charge ticket (charge lines + claim notes).
6. **Enforce + save** — the rules engine, not the LLM, has final say: units are clamped to MUE caps, NCCI-bundled codes are dropped, and links to ruled-out diagnoses are stripped regardless of what the LLM drafted. Writes the JSON to `output/<charge_id>.json` and returns it.

Three of the six phases call OpenAI (`gpt-4o`); the rest is deterministic Python.

## Setup

### Prerequisites
- Python 3.11+
- OpenAI API key

NLM Clinical Tables (ICD-10-CM, HCPCS) requires no key — it's a free, public, keyless API.

### Install
```bash
cd ~/Desktop/CodingAssist
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Configure
Copy `.env.example` to `.env` and fill in your key:
```bash
copy .env.example .env
```
```
OPENAI_API_KEY=sk-your-key-here
PORT=8025
```

## Run

```bash
python main.py
```

On the **first run** the service seeds its local RAG store with ICD-10-CM and HCPCS codes for the terms in `coding_seed_terms.json` (via the live NLM API) plus a curated CPT list (no live call). The store is persisted to `rag_db/` and reused on subsequent starts. Seeding failures are logged but don't crash startup.

Server runs at http://localhost:8025.

> Default port is **8025** (avoids conflict with Patient Timeline on 8001). RadiologyReporter uses 8024 in this monorepo so both can run side by side.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | Service identity |
| `GET` | `/api/v1/health` | Status, model, RAG record count |
| `GET` | `/api/v1/coding-edits/summary` | Counts/contents of loaded NCCI PTP edits and MUE limits (no AI call) |
| `POST` | `/api/v1/charges/generate` | Charge-capture pipeline — documents in, structured charge ticket out |

Interactive docs: http://localhost:8025/docs

Postman collection: import [postman_collection.json](postman_collection.json) (Postman → File → Import). Default `base_url` is `http://localhost:8025`. Includes all stress-test scenarios: happy path, NCCI bundling, MUE clamp, ruled-out diagnosis, medical necessity, multi-document conflict, prompt injection, polytrauma volume, radiology upstream chaining, and invalid-field 422 validation.

## Example request

`POST http://localhost:8025/api/v1/charges/generate`

```json
{
  "encounter_metadata": {
    "encounter_id": "ENC-100234",
    "patient_id": "P-55012",
    "date_of_service": "2026-06-15",
    "place_of_service": "11",
    "rendering_provider_npi": "1234567893",
    "payer_id": "AETNA-COMM"
  },
  "documents": [
    {
      "document_type": "progress_note",
      "text": "Established patient, 30 min visit. Type 2 diabetes mellitus, stable, A1c 6.9, continue metformin. Essential hypertension, stable on lisinopril 10mg."
    }
  ],
  "upstream_entities": null
}
```

Response is the full structured charge ticket (coded entities, compliance flags, charge lines, claim notes). Same JSON is also written to `output/ENC-100234-<timestamp>.json`.

## Project layout

```
CodingAssist/
├── main.py                          # FastAPI entry, lifespan seeds RAG on startup
├── .env.example                      # copy to .env and set OPENAI_API_KEY
├── postman_collection.json          # Postman API tests (all scenarios)
├── coding_edit_rules.json           # illustrative NCCI PTP edits + MUE limits
├── medical_necessity_policies.json  # illustrative LCD-style covered-indications
├── billing_data_guide.txt           # shorthand table + drafting/compliance rules
├── output_schema.json               # the response shape
├── coding_seed_terms.json           # ICD-10/HCPCS terms (live lookup) + curated CPT list
├── app/
│   ├── core/config.py               # Pydantic settings from .env
│   ├── models/schemas.py            # request/response Pydantic models (POS/NPI validators)
│   ├── ai/
│   │   ├── client.py                 # OpenAI client with retry logic
│   │   └── prompts.py                # builders for the 3 LLM calls
│   ├── rag/
│   │   ├── store.py                  # ChromaDB persistent store
│   │   └── seeder.py                 # startup seeding routine
│   ├── ontology/
│   │   ├── clinical_tables.py        # NLM Clinical Tables API client
│   │   ├── icd10.py                  # ICD-10-CM wrapper
│   │   └── hcpcs.py                  # HCPCS Level II wrapper
│   ├── rules/
│   │   └── edit_engine.py            # NCCI/MUE/medical-necessity rules engine
│   ├── services/
│   │   └── coding_service.py         # orchestrates the 6 phases
│   └── api/routes.py                 # FastAPI route definitions
├── tests/
│   ├── test_routes.py                # endpoint tests (mocked AI + RAG calls)
│   └── charge_request_fixtures.json  # shared request bodies for tests + Postman source
├── rag_db/                           # persisted Chroma store (gitignored)
└── output/                           # generated charge tickets (gitignored)
```

## Notes

- Keep `.env` out of version control — it's already in `.gitignore`.
- The RAG store on disk (`rag_db/`) survives restarts. Delete it if you want to force a full re-seed.
- The rules engine is authoritative, not the LLM: phase 6 re-enforces every blocking compliance flag in plain Python after drafting, so a sloppy or hallucinated LLM draft can't result in a non-compliant charge ticket.
- `coding_edit_rules.json` and `medical_necessity_policies.json` are illustrative samples, not the full CMS NCCI/MUE table or a complete LCD library.
- Logging is INFO level; every OpenAI call logs token usage.
- For radiology report generation, see the sibling project [RadiologyReporter](../RAdiology/).
