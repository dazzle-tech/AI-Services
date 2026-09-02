"""Tests for the handover orchestrator — chart assembly is attached to results."""

from unittest.mock import AsyncMock, patch

import pytest

from app.models.schemas import GenerateSummaryRequest
from app.services.nurse_handover_service import generate_shift_summaries


@pytest.mark.asyncio
async def test_shift_summaries_share_generated_at_and_current_status(
    critical_patient,
    valid_gpt_response_critical,
):
    request = GenerateSummaryRequest(
        shift_id="shift-1005-day",
        nurse_id="nurse_sarah_mitchell",
        patient=critical_patient,
    )

    with patch(
        "app.services.nurse_handover_service.call_gpt",
        new=AsyncMock(return_value=valid_gpt_response_critical),
    ):
        response = await generate_shift_summaries(request)

    assert response.generated_at is not None
    assert response.generated_at.tzinfo is not None
    assert len(response.results) == 1

    result = response.results[0]
    assert result.success is True
    assert result.current_status is not None
    assert result.current_status.generated_at == response.generated_at
    assert result.summary.generated_at == response.generated_at
    assert [a.name for a in result.current_status.allergies] == ["Penicillin"]
    assert [w.text for w in result.current_status.warnings] == ["Fall risk — bed rails up"]
    assert [p.name for p in result.current_status.pending_procedures] == ["Repeat chest X-ray"]
    assert result.current_status.diagnosis == critical_patient.diagnosis
    assert result.current_status.past_medical_history == critical_patient.past_medical_history
    assert result.current_status.hospital_course == critical_patient.hospital_course
    assert "**Situation**" in result.formatted_text
    assert "**Diagnosis**" in result.formatted_text
    assert "**Allergies**" in result.summary.formatted_text or "**Allergies**" in result.formatted_text
