"""Seed ViewDecoders for ORScribe analyze/case JSON.

Loaded at startup (and in tests) via DecoderService.upsert.
"""

from app.models.schemas import DecoderField, ViewDecoder
from app.services.decoder_service import DecoderService

OR_TIMELINE_DECODER = ViewDecoder(
    view_id="or_timeline",
    view_name="OR Timeline",
    fields=[
        DecoderField(
            field_name="Events",
            field_type="list",
            source_path="events",
            transform="direct",
        ),
        DecoderField(
            field_name="EventTimes",
            field_type="list",
            source_path="events[*].timestamp",
            transform="direct",
            required=False,
        ),
        DecoderField(
            field_name="EventTypes",
            field_type="list",
            source_path="events[*].type",
            transform="direct",
            required=False,
        ),
        DecoderField(
            field_name="EventSummary",
            field_type="string",
            source_path="events[*].description",
            transform="concat",
            transform_hint=" | ",
            required=False,
        ),
    ],
)

OR_MEDICATIONS_DECODER = ViewDecoder(
    view_id="or_medications",
    view_name="OR Medications",
    fields=[
        DecoderField(
            field_name="Medications",
            field_type="list",
            source_path="medications_administered",
            transform="direct",
        ),
        DecoderField(
            field_name="Drugs",
            field_type="list",
            source_path="medications_administered[*].drug",
            transform="direct",
            required=False,
        ),
        DecoderField(
            field_name="Doses",
            field_type="list",
            source_path="medications_administered[*].dose",
            transform="direct",
            required=False,
        ),
    ],
)

OR_COUNTS_DECODER = ViewDecoder(
    view_id="or_counts",
    view_name="OR Counts",
    fields=[
        DecoderField(
            field_name="Counts",
            field_type="list",
            source_path="instrument_counts",
            transform="direct",
            required=False,
        ),
        DecoderField(
            field_name="CountResults",
            field_type="list",
            source_path="instrument_counts[*].result",
            transform="direct",
            required=False,
        ),
    ],
)

OR_CHECKLIST_DECODER = ViewDecoder(
    view_id="or_checklist",
    view_name="WHO Surgical Safety Checklist",
    fields=[
        DecoderField(
            field_name="SignInCompleted",
            field_type="boolean",
            source_path="sign_in.completed",
            transform="direct",
        ),
        DecoderField(
            field_name="SignInConfirmed",
            field_type="list",
            source_path="sign_in.items_confirmed",
            transform="direct",
            required=False,
        ),
        DecoderField(
            field_name="SignInMissing",
            field_type="list",
            source_path="sign_in.items_missing",
            transform="direct",
            required=False,
        ),
        DecoderField(
            field_name="TimeOutCompleted",
            field_type="boolean",
            source_path="time_out.completed",
            transform="direct",
        ),
        DecoderField(
            field_name="TimeOutConfirmed",
            field_type="list",
            source_path="time_out.items_confirmed",
            transform="direct",
            required=False,
        ),
        DecoderField(
            field_name="TimeOutMissing",
            field_type="list",
            source_path="time_out.items_missing",
            transform="direct",
            required=False,
        ),
        DecoderField(
            field_name="SignOutCompleted",
            field_type="boolean",
            source_path="sign_out.completed",
            transform="direct",
        ),
        DecoderField(
            field_name="SignOutConfirmed",
            field_type="list",
            source_path="sign_out.items_confirmed",
            transform="direct",
            required=False,
        ),
        DecoderField(
            field_name="SignOutMissing",
            field_type="list",
            source_path="sign_out.items_missing",
            transform="direct",
            required=False,
        ),
    ],
)

OR_ROLES_DECODER = ViewDecoder(
    view_id="or_roles",
    view_name="OR Roles",
    fields=[
        DecoderField(
            field_name="RoleMap",
            field_type="object",
            source_path="role_map",
            transform="direct",
        ),
        DecoderField(
            field_name="NeedsReview",
            field_type="boolean",
            source_path="needs_review",
            transform="direct",
        ),
        DecoderField(
            field_name="RoleReasoning",
            field_type="string",
            source_path="role_reasoning",
            transform="direct",
            required=False,
        ),
        DecoderField(
            field_name="ProcedureType",
            field_type="string",
            source_path="procedure_type",
            transform="direct",
            required=False,
        ),
    ],
)

SEED_DECODERS = (
    OR_TIMELINE_DECODER,
    OR_MEDICATIONS_DECODER,
    OR_COUNTS_DECODER,
    OR_CHECKLIST_DECODER,
    OR_ROLES_DECODER,
)


def seed_default_decoders(db) -> None:
    service = DecoderService(db)
    for decoder in SEED_DECODERS:
        service.upsert(decoder)
