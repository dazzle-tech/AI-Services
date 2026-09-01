"""Unit tests for SOAP summarization — no hallucination."""

import pytest

from app.ai.summarization import summarize_transcript
from app.ai.unified_prompts import PURPOSE_FRAGMENTS, TranscriptionRequest, build_system_prompt
from app.models.schemas import ClinicalDocument, NarrativeSummary, SOAPSummary, TranscriptionRequestOptions
from tests.fixtures.sample_transcripts import SUMMARIZATION_ROLE_MAP, SUMMARIZATION_SEGMENTS


def test_summarization_only_uses_transcript_content():
    summary = summarize_transcript(SUMMARIZATION_SEGMENTS, SUMMARIZATION_ROLE_MAP)
    combined = " ".join(
        [
            summary.subjective,
            summary.objective,
            summary.assessment,
            summary.plan,
            summary.follow_up,
            " ".join(summary.medications_mentioned),
        ]
    ).lower()

    assert "headache" in combined
    assert "diabetes" not in combined
    assert "blood pressure" not in combined
    assert "hypertension" not in combined


def test_summarization_marks_missing_sections():
    summary = summarize_transcript(SUMMARIZATION_SEGMENTS, SUMMARIZATION_ROLE_MAP)
    assert summary.subjective != ""
    assert summary.assessment == "Not discussed" or "not discussed" in summary.assessment.lower()


@pytest.mark.parametrize(
    "purpose,expected_type,fragment_key",
    [
        ("soap_note", SOAPSummary, "soap_note"),
        ("summary", NarrativeSummary, "summary"),
        ("clinical_document", ClinicalDocument, "clinical_document"),
    ],
)
def test_summarization_purpose_selects_schema_and_prompt_fragment(purpose, expected_type, fragment_key):
    req = TranscriptionRequest(
        context_type="appointment",
        attendees=["doctor", "patient"],
        purpose=purpose,
        detail_level="key_points",
    )
    prompt = build_system_prompt(req)
    assert PURPOSE_FRAGMENTS[fragment_key] in prompt
    output = summarize_transcript(
        SUMMARIZATION_SEGMENTS,
        SUMMARIZATION_ROLE_MAP,
        prompt_options=TranscriptionRequestOptions(
            context_type="appointment",
            attendees=["doctor", "patient"],
            purpose=purpose,
            detail_level="key_points",
        ),
    )
    assert isinstance(output, expected_type)
