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

### Limitations
- Only representative slices are reviewed, not the full volume.
- Sub-millimeter findings may be missed.
- This is an assistive AI tool. Full radiologist review of all slices is required.

## Local run
```powershell
cd MedicalImageInterpretationAssistService
python -m venv .venv
. .venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload --port 8015
```

## Postman
Import:
- `postman/Xray_Interpretation_Assist.postman_collection.json`

## Tests
```powershell
cd MedicalImageInterpretationAssistService
python -m pytest -q
```
