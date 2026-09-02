"""POST /summary/generate

Generates SBAR summaries for every patient in the request. Patients are processed
concurrently; per-patient failures are isolated and reported in the results array
rather than aborting the whole batch.

Summaries come back as status "draft" — the nurse reviews them in the dashboard and
the agent persists the confirmed version to hospital.db.
"""
from fastapi import APIRouter

from app.models.schemas import GenerateSummaryRequest, GenerateSummaryResponse
from app.services.nurse_handover_service import generate_shift_summaries

router = APIRouter()


@router.post(
    "/generate",
    response_model=GenerateSummaryResponse,
    summary="Generate SBAR summaries for a shift",
)
async def generate_summaries(body: GenerateSummaryRequest) -> GenerateSummaryResponse:
    return await generate_shift_summaries(body)
