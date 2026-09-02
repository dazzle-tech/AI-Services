"""Markdown rendering for handover output. Section headlines use **bold**."""

from typing import Optional

from app.models.schemas import PatientCurrentStatus, SBARSummary


def _section(title: str, body: str) -> str:
    return f"**{title}**\n{body.strip() if body and body.strip() else 'not recorded'}"


def render_sbar_markdown(summary: SBARSummary) -> str:
    flags = "\n".join(f"- {item}" for item in summary.flags) if summary.flags else "None"
    return "\n\n".join(
        [
            f"**Priority:** {summary.priority.value}",
            _section("Situation", summary.situation),
            _section("Background", summary.background),
            _section("Assessment", summary.assessment),
            _section("Recommendation", summary.recommendation),
            _section("Flags", flags),
        ]
    )


def render_status_markdown(status: PatientCurrentStatus) -> str:
    allergies = (
        "\n".join(
            f"- {a.name}" + (f" ({a.category})" if a.category else "")
            for a in status.allergies
        )
        or "None"
    )
    warnings = (
        "\n".join(
            f"- {w.text}" + (f" ({w.category})" if w.category else "")
            for w in status.warnings
        )
        or "None"
    )
    vitals = (
        "\n".join(
            f"- {v.type}: {v.value}"
            + (f" {v.unit}" if v.unit else "")
            + (f" (last: {v.recorded_at})" if v.recorded_at else "")
            for v in status.vital_signs
        )
        or "None recorded"
    )
    procedures = (
        "\n".join(
            f"- {p.name}"
            + (f" | {p.status}" if p.status else "")
            + (f" | {p.scheduled_at}" if p.scheduled_at else "")
            for p in status.pending_procedures
        )
        or "None"
    )
    return "\n\n".join(
        [
            _section("Diagnosis", status.diagnosis or ""),
            _section("Past medical history", status.past_medical_history or ""),
            _section("Hospital course", status.hospital_course or ""),
            _section("Allergies", allergies),
            _section("Warnings", warnings),
            _section("Vital signs", vitals),
            _section("Pending OP / procedures", procedures),
        ]
    )


def render_handover_document(
    summary: Optional[SBARSummary] = None,
    current_status: Optional[PatientCurrentStatus] = None,
) -> str:
    blocks = []
    if current_status is not None:
        blocks.append(render_status_markdown(current_status))
    if summary is not None:
        blocks.append(render_sbar_markdown(summary))
    return "\n\n".join(blocks).strip()
