# Radiology Template Selection & Autofill Service

Two-stage FastAPI service for radiology report drafting:

1. **Template Selection** — RAG over a managed repository of radiology report templates (CT, MRI, Ultrasound, X-ray, Mammography). A static-override flag lets callers bypass RAG and force a specific template.
2. **Autofill** — An LLM populates the selected template's fields from a clinician's raw dictation, then renders a plain-text report.

See `docs/Service Specification_ Template Selection & Autofill System.md` for the full spec.

---

## Requirements

- **Python:** 3.10+
- See `requirements.txt` (FastAPI, OpenAI, ChromaDB, sentence-transformers, pytest)

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows PowerShell
pip install -r requirements.txt
copy .env.example .env             # then edit OPENAI_API_KEY
```

On first run, sentence-transformers will download the embedding model (`all-MiniLM-L6-v2`, ~90 MB).

## Run

```bash
python main.py
```

- Service: `http://localhost:8013`
- Interactive docs: `http://localhost:8013/docs`

## Endpoints

| Method | Path                          | Description |
|--------|-------------------------------|-------------|
| GET    | `/`                           | Service info |
| GET    | `/health`                     | Health check |
| GET    | `/templates`                  | List available templates |
| GET    | `/templates/{template_id}`    | Full template (fields and metadata) |
| GET    | `/samples`                    | List sample clinician inputs (for testing) |
| GET    | `/samples/{key}`              | Get one sample input |
| POST   | `/select-template`            | **Stage 1**: RAG (or static) template selection |
| POST   | `/autofill`                   | **Stage 2**: Autofill a chosen template from input |
| POST   | `/select-and-fill`            | One-shot: select + autofill |

## Seed Templates

| `template_id`            | Modality      | Region          |
|--------------------------|---------------|-----------------|
| `ct_chest`               | CT            | Chest           |
| `mri_brain`              | MRI           | Brain           |
| `mri_lumbar_spine`       | MRI           | Lumbar Spine    |
| `us_abdomen_ruq`         | Ultrasound    | Abdomen (RUQ)   |
| `mammography_screening`  | Mammography   | Breast          |

Add a new template by dropping a JSON file into `data/templates/` matching the existing schema (`Template` in `models/schemas.py`). Restart the service to re-index.

## Configuration (`.env`)

| Variable             | Default                     | Purpose |
|----------------------|-----------------------------|---------|
| `OPENAI_API_KEY`     | _(required for real autofill)_ | OpenAI key |
| `OPENAI_MODEL`       | `gpt-4o`                    | Model for autofill |
| `OPENAI_TEMPERATURE` | `0.1`                       | LLM temperature |
| `EMBEDDING_MODEL`    | `all-MiniLM-L6-v2`          | sentence-transformer model |
| `TEMPLATES_DIR`      | `data/templates`            | Where template JSONs live (resolved relative to project) |
| `VECTOR_STORE_PATH`  | `vector_store_templates`    | ChromaDB persistence directory (resolved relative to project) |
| `API_PORT`           | `8013`                      | Listening port |
| `CORS_ORIGINS`       | `*`                         | Comma-separated origins, or `*` |
| `MOCK_LLM`           | `false`                     | If `true`, skip OpenAI and use deterministic stub (for tests / offline) |

## Postman

Import `radiology_template_autofill.postman_collection.json`. Default `base_url` is `http://localhost:8013` — override via the collection variable if needed.

## Tests

```bash
pytest tests/ -v
```

Tests force `MOCK_LLM=true` so they run without an OpenAI key. They cover:

- Meta / health
- Template listing and detail
- RAG selection across modalities (CT, MRI, Ultrasound, X-ray)
- Static override + error cases
- Autofill happy path + missing-required-field flagging
- End-to-end `select-and-fill`

## Architecture

```
main.py
  ├── services/template_repository.py   # loads JSON templates from disk
  ├── services/rag_selector.py          # ChromaDB + sentence-transformers
  └── services/autofill_service.py      # OpenAI LLM, MOCK_LLM fallback
models/schemas.py                        # Pydantic request/response models
data/templates/*.json                    # template definitions
data/sample_inputs.py                    # sample dictations for testing
```

## Notes & Caveats

- Prototype quality: no auth, no rate limiting, no fine-tuning.
- The ChromaDB collection is rebuilt on each startup so on-disk template edits take effect after a restart.
- The autofill prompt instructs the model not to invent findings, but you should still validate clinically before use.
