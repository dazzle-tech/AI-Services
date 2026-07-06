# Medical Image Interpretation Assist Service (X-ray MVP)

## X-ray Interpretation Assist Service

This service supports **X-ray interpretation only**, starting with **chest X-ray**.

## Safety disclaimer (required)
**Assistive AI only. Radiologist review required. Not for final diagnosis.**

The service only returns suspected/possible AI candidate findings and never confirms diagnosis.

## Supported exam types
- `XR_CHEST`
- `XR_CHEST_PA`
- `XR_CHEST_AP`
- `XR_CHEST_LATERAL`
- `XR_UNKNOWN`

## Input and output
- Input: DICOM CR/DX study as zip or single DICOM file, or a common image file (png/jpg/jpeg/webp/bmp/tiff) for chest X-ray.
- Output: structured suspected candidate findings JSON with `findings`, `critical_alert`, and disclaimer.

## MVP findings
- `PNEUMOTHORAX`
- `PLEURAL_EFFUSION`
- `LUNG_OPACITY`
- `CONSOLIDATION`
- `ATELECTASIS`
- `CARDIOMEGALY`
- `PULMONARY_EDEMA`
- no acute candidate finding when nothing is detected

## Modalities
- Accepted: `CR`, `DX`
- Rejected as unsupported: `CT`, `MR/MRI`, `US`

## Model layer
- `app/interpretation/xray_model.py` defines `run_xray_model(image_path, exam_type)`.
- Current MVP uses TorchXRayVision DenseNet pretrained weights.
- If model inference fails/unavailable, API returns `REVIEW_REQUIRED` gracefully.

### Local Ollama guidance
- `qwen3:1.7b` is a text-only model and is not suitable for image interpretation.
- Image interpretation requires a vision-capable local model configured via `VISION_MODEL` such as `qwen2.5vl:3b`, or it will be skipped with `REVIEW_REQUIRED`.
- Set `ENABLE_IMAGE_MODEL=false` to skip multimodal interpretation safely without crashing the application.
- If a configured image model does not support image input, the service returns HTTP `200` with `status="REVIEW_REQUIRED"`.
- `OPENAI_MODEL` is not used for image interpretation in this service. Keep that setting in Report Filling, not here.
- Report Filling can use `qwen3:1.7b` because it is text-only.
- Image Interpretation must use `qwen2.5vl:3b` or another vision-capable model.

Recommended local `.env`:
```dotenv
OPENAI_BASE_URL=http://localhost:11434/v1
OPENAI_API_KEY=ollama
ENABLE_IMAGE_MODEL=true
VISION_MODEL=qwen2.5vl:3b
VISION_IMAGE_URL_AS_STRING=true
OPENAI_TIMEOUT=180
OPENAI_MAX_RETRIES=1
```

Note: TorchXRayVision may download pretrained weights on first run (network access required unless the weights are already cached).

## API endpoints
1. `GET /api/v1/radiology/xray-interpretation/health`
2. `POST /api/v1/radiology/xray-interpretation/dicom`

## CT Interpretation Endpoint

Requires `OPENAI_API_KEY` to be set.

### Supported modality
- `CT` only (not MR, US, NM)

### Accepted input
- DICOM CT study as zip (multi-slice series) or single `.dcm` file.
  A zip with a full axial series is strongly recommended for best accuracy.

### Endpoints
1. `GET  /api/v1/radiology/ct-interpretation/health`
2. `POST /api/v1/radiology/ct-interpretation/dicom`

### How it works
Up to 6 representative axial slices are extracted evenly across the series
(skipping the first and last 10%), converted to windowed PNGs, and sent to
GPT-4o vision together in a single prompt. Findings are returned as structured
JSON with the same schema as the X-ray endpoint.

When running locally against Ollama, use a vision-capable model for CT or X-ray
interpretation. If only a text model such as `qwen3:1.7b` is configured, the
service will skip image interpretation and return a safe `REVIEW_REQUIRED`
response instead of attempting a multimodal request.

### Limitations
- Only representative slices are reviewed, not the full volume.
- Sub-millimeter findings may be missed.
- This is an assistive AI tool. Full radiologist review of all slices is required.

## Local run
```powershell
cd MedicalImageInterpretationAssistService
ollama pull qwen2.5vl:3b
ollama list
python -m venv .venv
. .venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8015
```

## Postman
Import:
- `postman/Xray_Interpretation_Assist.postman_collection.json`

## Tests
```powershell
cd MedicalImageInterpretationAssistService
python -m pytest -q
```
