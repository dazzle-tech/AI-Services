"""
nurse_handover_service.py
-------------------------
Orchestrator — the single public API for the NurseHandOver generation pipeline.


This module wires together prompt_builder → gpt_service → summary_parser.
Routes and tests call this module; they never call the sub-services directly.

Key design choices:
- Exactly one patient per API call.
- Pipeline errors are captured in PatientSummaryResult.error rather than
  aborting with an unhandled exception.
"""

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
    handover_nurse: str = "",
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
        user_prompt   = build_user_prompt(
            patient,
            current_status=current_status,
            handover_nurse=handover_nurse,
        )
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
            formatted_text=render_handover_document(
                summary,
                current_status,
                handover_nurse=handover_nurse,
                generated_at=stamp,
            ),
        )

    except Exception as e:
        return PatientSummaryResult(
            patient_id=patient.patient_id,
            success=False,
            current_status=current_status,
            formatted_text=render_handover_document(
                None,
                current_status,
                handover_nurse=handover_nurse,
                generated_at=stamp,
            ),
            error=str(e),
        )


async def generate_shift_summaries(request: GenerateSummaryRequest) -> GenerateSummaryResponse:
    """
    Generates a draft SBAR for the single patient in the request.
    """
    generated_at = datetime.now(timezone.utc)
    result = await generate_patient_summary(
        request.patient,
        generated_at=generated_at,
        handover_nurse=request.handover_nurse,
    )
    body = result.formatted_text or ""
    if not result.success and result.error:
        body = f"{body}\n\n**Error**\n{result.error}".strip()

    return GenerateSummaryResponse(
        formatted_text=body,
        generated_by_ai_for=request.handover_nurse,
        generated_at=generated_at,
    )
