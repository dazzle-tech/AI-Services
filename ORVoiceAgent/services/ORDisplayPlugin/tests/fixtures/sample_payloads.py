"""Sample ORScribe analyze / case payloads."""

from app.fixtures.decoders import (
    OR_CHECKLIST_DECODER,
    OR_COUNTS_DECODER,
    OR_MEDICATIONS_DECODER,
    OR_ROLES_DECODER,
    OR_TIMELINE_DECODER,
)

ANALYZE_AUDIO = {
    "raw_transcript": {
        "segments": [
            {
                "speaker_label": "SPEAKER_00",
                "start_time": 0.0,
                "end_time": 8.0,
                "text": "Sign in complete. Patient identity confirmed, site marked.",
            },
            {
                "speaker_label": "SPEAKER_01",
                "start_time": 28.5,
                "end_time": 35.0,
                "text": "Giving propofol 100 milligrams.",
            },
        ]
    },
    "role_map": {
        "SPEAKER_00": {"role": "surgeon", "confidence": "high", "needs_review": False},
        "SPEAKER_01": {"role": "anesthetist", "confidence": "high", "needs_review": False},
        "SPEAKER_02": {"role": "nurse", "confidence": "medium", "needs_review": False},
    },
    "role_reasoning": "Speaker 0 leads sign-in and incision; speaker 1 gives anesthesia; speaker 2 reports counts.",
    "needs_review": False,
    "timeline": {
        "events": [
            {
                "timestamp": "00:00:22",
                "type": "incision",
                "speaker_role": "surgeon",
                "description": "Incision made",
            },
            {
                "timestamp": "00:01:10",
                "type": "medication",
                "speaker_role": "anesthetist",
                "description": "Propofol given",
            },
        ],
        "medications_administered": [
            {
                "timestamp": "00:01:10",
                "drug": "propofol",
                "dose": "100 mg",
                "administered_by_role": "anesthetist",
            }
        ],
        "instrument_counts": [
            {
                "timestamp": "00:14:02",
                "type": "sponge_count",
                "result": "correct",
                "reported_by_role": "nurse",
            }
        ],
    },
    "checklist": {
        "sign_in": {
            "completed": True,
            "items_confirmed": ["identity", "site marked"],
            "items_missing": [],
        },
        "time_out": {
            "completed": True,
            "items_confirmed": ["team introductions"],
            "items_missing": [],
        },
        "sign_out": {
            "completed": True,
            "items_confirmed": ["procedure recorded", "specimen labeled"],
            "items_missing": [],
        },
    },
}

CASE_RECORD = {
    "id": "11111111-1111-1111-1111-111111111111",
    "status": "completed",
    "procedure_type": "laparoscopic cholecystectomy",
    "needs_review": False,
    "role_map": ANALYZE_AUDIO["role_map"],
    "role_reasoning": ANALYZE_AUDIO["role_reasoning"],
    "timeline": ANALYZE_AUDIO["timeline"],
    "medications": ANALYZE_AUDIO["timeline"]["medications_administered"],
    "instrument_counts": ANALYZE_AUDIO["timeline"]["instrument_counts"],
    "checklist_result": ANALYZE_AUDIO["checklist"],
}


def full_or_reshape_request() -> dict:
    return {
        "context": "operating_room",
        "purpose": "timeline",
        "views": [
            OR_TIMELINE_DECODER.model_dump(),
            OR_MEDICATIONS_DECODER.model_dump(),
            OR_COUNTS_DECODER.model_dump(),
            OR_CHECKLIST_DECODER.model_dump(),
            OR_ROLES_DECODER.model_dump(),
        ],
        "stage1_output": ANALYZE_AUDIO,
    }
