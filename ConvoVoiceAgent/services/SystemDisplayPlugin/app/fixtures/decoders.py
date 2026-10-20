"""Seed ViewDecoders for the three chart views this service maps onto.

Loaded at startup (and in tests) via DecoderService.upsert — same store as POST /decoders.

The clinical summary is written once, upstream: ConvoScribe's soap_note output carries
`chart` (one string per SOAP chart field), `vitals` and `measurements`. Every seeded field is a
direct copy of those values, so reshaping a seeded view makes no LLM call and cannot reword a
clinical term. `summarize` / `extract` transforms remain available for decoders registered
through POST /decoders.
"""

from app.models.schemas import DecoderField, ViewDecoder
from app.services.decoder_service import DecoderService

SOAP_CHART_FIELDS = (
    "ChiefComplaint",
    "HPI",
    "MedicalHistory",
    "SurgicalHistory",
    "FamilyAndSocialHistory",
    "OtherSubjective",
    "Vitals",
    "PhysicalExamination",
    "Assessments",
    "DiagnosticImagesAndTests",
    "Procedures",
    "TreatmentPlans",
)

SOAP_NOTE_DECODER = ViewDecoder(
    view_id="soap_note",
    view_name="SOAP Note",
    fields=[
        DecoderField(
            field_name=name,
            field_type="string",
            source_path=f"chart.{name}",
            transform="direct",
            required=False,
        )
        for name in SOAP_CHART_FIELDS
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
            transform="direct",
            required=False,
        ),
    ],
)

SEED_DECODERS = (SOAP_NOTE_DECODER, VITAL_SIGNS_DECODER, MEASUREMENT_DECODER)


def seed_default_decoders(db) -> None:
    service = DecoderService(db)
    for decoder in SEED_DECODERS:
        service.upsert(decoder)
