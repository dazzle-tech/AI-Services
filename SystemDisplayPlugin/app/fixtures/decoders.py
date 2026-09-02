"""Seed ViewDecoders for the three chart views this service maps onto.

Loaded at startup (and in tests) via DecoderService.upsert — same store as POST /decoders.

STAGE-1 GAP (do not invent mappings):
- SOAP chart fields (ChiefComplaint, HPI, …) read ConvoScribe `subjective` / `objective` /
  `assessment` / `plan`. Assessments is a direct copy; the rest summarize those sections.
- ConvoScribe AnalyzeAudioResponse has no structured `vitals` or `measurements`.
- ORScribe CaseResponse / AnalyzeAudioResponse has timeline, medications, instrument_counts,
  checklist, and timeline event type `vitals_report` (free-text description), not a structured
  `vitals` or `measurements` object with temperature_c / weight_kg / etc.
Until those services extract structured vitals/measurements, those source_paths will miss and
the Vital Signs / Measurement views will warn (optional fields) or fail required fields.
"""

from app.models.schemas import DecoderField, ViewDecoder
from app.services.decoder_service import DecoderService

SOAP_NOTE_DECODER = ViewDecoder(
    view_id="soap_note",
    view_name="SOAP Note",
    fields=[
        DecoderField(
            field_name="ChiefComplaint",
            field_type="string",
            source_path="subjective",
            transform="summarize",
            transform_hint="the patient's main reason for the visit, in one short phrase as they described it",
            required=False,
        ),
        DecoderField(
            field_name="HPI",
            field_type="string",
            source_path="subjective",
            transform="summarize",
            transform_hint="history of present illness: onset, duration, character, severity and any aggravating or relieving factors mentioned",
            required=False,
        ),
        DecoderField(
            field_name="MedicalHistory",
            field_type="string",
            source_path="subjective",
            transform="summarize",
            transform_hint="any past medical conditions, chronic illnesses or current medications mentioned; leave empty if none discussed",
            required=False,
        ),
        DecoderField(
            field_name="SurgicalHistory",
            field_type="string",
            source_path="subjective",
            transform="summarize",
            transform_hint="any previous operations or procedures mentioned; leave empty if none discussed",
            required=False,
        ),
        DecoderField(
            field_name="FamilyAndSocialHistory",
            field_type="string",
            source_path="subjective",
            transform="summarize",
            transform_hint="family history, smoking, alcohol, occupation or living situation mentioned; leave empty if none discussed",
            required=False,
        ),
        DecoderField(
            field_name="OtherSubjective",
            field_type="string",
            source_path="subjective",
            transform="summarize",
            transform_hint="anything else the patient or companion reported that does not fit the other subjective fields",
            required=False,
        ),
        DecoderField(
            field_name="Vitals",
            field_type="string",
            source_path="objective",
            transform="summarize",
            transform_hint="vital sign findings stated aloud during the encounter, as a short readable line",
            required=False,
        ),
        DecoderField(
            field_name="PhysicalExamination",
            field_type="string",
            source_path="objective",
            transform="summarize",
            transform_hint="examination findings the clinician described, by system where possible",
            required=False,
        ),
        DecoderField(
            field_name="Assessments",
            field_type="string",
            source_path="assessment",
            transform="direct",
            transform_hint=None,
            required=False,
        ),
        DecoderField(
            field_name="DiagnosticImagesAndTests",
            field_type="string",
            source_path="plan",
            transform="summarize",
            transform_hint="imaging, labs or other investigations ordered; leave empty if none were ordered",
            required=False,
        ),
        DecoderField(
            field_name="Procedures",
            field_type="string",
            source_path="plan",
            transform="summarize",
            transform_hint="procedures performed or planned; leave empty if none were mentioned",
            required=False,
        ),
        DecoderField(
            field_name="TreatmentPlans",
            field_type="string",
            source_path="plan",
            transform="summarize",
            transform_hint="medications, advice, referrals and follow-up instructions given to the patient",
            required=False,
        ),
    ],
)

VITAL_SIGNS_DECODER = ViewDecoder(
    view_id="vital_signs",
    view_name="Vital Signs",
    fields=[
        DecoderField(field_name="Temperature", field_type="string", source_path="vitals.temperature_c", transform="direct"),
        DecoderField(field_name="SpO2", field_type="string", source_path="vitals.spo2_pct", transform="direct"),
        DecoderField(field_name="BPSystolic", field_type="string", source_path="vitals.bp_systolic", transform="direct"),
        DecoderField(field_name="BPDiastolic", field_type="string", source_path="vitals.bp_diastolic", transform="direct"),
        DecoderField(field_name="PulseRate", field_type="string", source_path="vitals.pulse_rate", transform="direct"),
        DecoderField(field_name="Pain", field_type="string", source_path="vitals.pain_score", transform="direct"),
        DecoderField(field_name="RespiratoryRate", field_type="string", source_path="vitals.resp_rate", transform="direct"),
    ],
)

MEASUREMENT_DECODER = ViewDecoder(
    view_id="measurement",
    view_name="Measurement",
    fields=[
        DecoderField(field_name="WeightKg", field_type="string", source_path="measurements.weight_kg", transform="direct"),
        DecoderField(field_name="HeightLengthCm", field_type="string", source_path="measurements.height_cm", transform="direct"),
        DecoderField(
            field_name="BMI",
            field_type="string",
            source_path="measurements.bmi",
            transform="direct",
            required=False,
        ),
        DecoderField(
            field_name="HeadCircumferenceCm",
            field_type="string",
            source_path="measurements.head_circumference_cm",
            transform="direct",
            required=False,
        ),
        DecoderField(
            field_name="Note",
            field_type="string",
            source_path="measurements.note",
            transform="summarize",
            transform_hint="condense any free-text note from the encounter into one short clinical remark",
            required=False,
        ),
    ],
)

SEED_DECODERS = (SOAP_NOTE_DECODER, VITAL_SIGNS_DECODER, MEASUREMENT_DECODER)


def seed_default_decoders(db) -> None:
    service = DecoderService(db)
    for decoder in SEED_DECODERS:
        service.upsert(decoder)
