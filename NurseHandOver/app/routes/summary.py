"""POST /summary/generate

Generates SBAR summaries for every patient in the request. Patients are processed
concurrently; per-patient failures are isolated and reported in the results array
rather than aborting the whole batch.

Summaries come back as status "draft" — the nurse reviews them in the dashboard and
the agent persists the confirmed version to hospital.db.

No request headers are required, including Content-Type: the body is parsed as JSON
as long as it is valid JSON.
"""
import json

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import ValidationError

from app.models.schemas import GenerateSummaryRequest, GenerateSummaryResponse
from app.services.nurse_handover_service import generate_shift_summaries

router = APIRouter()


@router.post(
    "/generate",
    response_model=GenerateSummaryResponse,
    summary="Generate SBAR summaries for a shift",
)
async def generate_summaries(request: Request) -> GenerateSummaryResponse:
    raw = await request.body()
    if not raw.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request body is required",
        )
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Request body must be JSON: {exc}",
        ) from exc
    try:
        body = GenerateSummaryRequest.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=json.loads(exc.json()),
        ) from exc
    return await generate_shift_summaries(body)
