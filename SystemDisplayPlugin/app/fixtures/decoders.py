"""Seed ViewDecoders for the three chart views this service maps onto.

Loaded at startup (and in tests) via DecoderService.upsert — same store as POST /decoders.

STAGE-1 GAP (do not invent mappings):
- ConvoScribe AnalyzeAudioResponse / SOAPSummary has subjective/objective/assessment/plan
  (nested under `summary` on the /analyze response). It has no `vitals` or `measurements`.
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
        DecoderField(field_name="Subjective", field_type="string", source_path="subjective", transform="direct"),
        DecoderField(field_name="Objective", field_type="string", source_path="objective", transform="direct"),
        DecoderField(field_name="Assessment", field_type="string", source_path="assessment", transform="direct"),
        DecoderField(field_name="Plan", field_type="string", source_path="plan", transform="direct"),
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
