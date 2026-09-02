"""
nurse_handover_service.py
-------------------------
Orchestrator — the single public API for the NurseHandOver generation pipeline.


This module wires together prompt_builder → gpt_service → summary_parser.
Routes (added later) and tests call this module; they never call the sub-services
directly. This keeps the AI pipeline's internal structure invisible to callers.

Key design choices:
- One GPT call per patient (isolated failures, independent retries).
- All patients in a batch are processed concurrently via asyncio.gather.
- Per-patient errors are captured in PatientSummaryResult.error rather than
  raising exceptions, so one failed patient never aborts the whole shift.
"""

import asyncio
from datetime import datetime, timezone

from app.models.schemas import (
    Patient,
    PatientSummaryResult,
    GenerateSummaryRequest,
    GenerateSummaryResponse,
)
from app.services.chart_assembler import assemble_current_status
from app.services.format_markdown import render_handover_document
from app.services.prompt_builder import get_system_prompt, build_user_prompt
from app.services.gpt_service import call_gpt
from app.services.summary_parser import parse_and_validate


async def generate_patient_summary(
    patient: Patient,
    generated_at: datetime | None = None,
) -> PatientSummaryResult:
    """
    Runs the full pipeline for a single patient:
        1. Assemble current-status chart (filter resolved / latest vitals)
        2. Build prompts
        3. Call GPT-4o
        4. Parse and validate response

    Returns a PatientSummaryResult with success=True and a populated summary,
    or success=False with an error message if anything in the pipeline fails.
    """
    stamp = generated_at or datetime.now(timezone.utc)
    current_status = assemble_current_status(patient, generated_at=stamp)

    try:
        system_prompt = get_system_prompt()
        user_prompt   = build_user_prompt(patient, current_status=current_status)
        raw_response  = await call_gpt(system_prompt, user_prompt)
        summary       = parse_and_validate(
            raw_response,
            patient.patient_id,
            generated_at=stamp,
        )

        return PatientSummaryResult(
            patient_id=patient.patient_id,
            success=True,
            summary=summary,
            current_status=current_status,
            formatted_text=render_handover_document(summary, current_status),
        )

    except Exception as e:
        return PatientSummaryResult(
            patient_id=patient.patient_id,
            success=False,
            current_status=current_status,
            formatted_text=render_handover_document(None, current_status),
            error=str(e),
        )


async def generate_shift_summaries(request: GenerateSummaryRequest) -> GenerateSummaryResponse:
    """
    Processes all patients in the request concurrently and returns a draft
    GenerateSummaryResponse containing one result per patient.

    The response has status="draft" — it becomes "confirmed" only after the
    nurse reviews and calls /confirm-handoff (handled by routes + data_store).
    """
    generated_at = datetime.now(timezone.utc)
    tasks = [generate_patient_summary(p, generated_at=generated_at) for p in request.patients]
    results = await asyncio.gather(*tasks)

    return GenerateSummaryResponse(
        shift_id=request.shift_id,
        request_id=request.request_id or request.shift_id,
        encounter_id=request.encounter_id,
        status="draft",
        generated_at=generated_at,
        results=list(results),
    )
