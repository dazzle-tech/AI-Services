"""Sample stage-1 payloads matching ConvoScribe SOAP / ORScribe timeline shapes."""

SOAP_NOTE = {
    "subjective": "Patient reports a 3-day frontal headache without fever.",
    "objective": "Alert, afebrile, neurological exam unremarkable.",
    "assessment": "Tension-type headache.",
    "plan": "Ibuprofen as needed. Follow up in two weeks if symptoms persist.",
    "medications_mentioned": ["ibuprofen"],
    "follow_up": "two weeks",
    "flags": [],
}

TIMELINE = {
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
    "instrument_counts": [],
}

EHR_SOAP_CARD = {
    "view_id": "ehr_soap_card",
    "view_name": "EHR SOAP card",
    "fields": [
        {
            "field_name": "hpi",
            "field_type": "string",
            "source_path": "subjective",
            "transform": "direct",
            "required": True,
        },
        {
            "field_name": "exam",
            "field_type": "string",
            "source_path": "objective",
            "transform": "direct",
            "required": True,
        },
        {
            "field_name": "dx",
            "field_type": "string",
            "source_path": "assessment",
            "transform": "direct",
            "required": True,
        },
        {
            "field_name": "meds",
            "field_type": "list",
            "source_path": "medications_mentioned",
            "transform": "direct",
            "required": True,
        },
        {
            "field_name": "plan_brief",
            "field_type": "string",
            "source_path": "plan",
            "transform": "summarize",
            "transform_hint": "One short sentence, no new clinical facts",
            "required": True,
        },
    ],
}

# Flattened SOAP + assumed vitals/measurements objects. ConvoScribe/ORScribe do not
# currently emit `vitals` or `measurements`; this is the contract we map onto.
ENCOUNTER_STAGE1 = {
    **SOAP_NOTE,
    "vitals": {
        "temperature_c": "36.8",
        "spo2_pct": "98",
        "bp_systolic": "122",
        "bp_diastolic": "78",
        "pulse_rate": "72",
        "pain_score": "2",
        "resp_rate": "16",
    },
    "measurements": {
        "weight_kg": "71.4",
        "height_cm": "168",
        "bmi": "25.3",
        "head_circumference_cm": "55",
        "note": "Weight taken after shoes removed; patient reports recent appetite loss.",
    },
}

ENCOUNTER_STAGE1_OPTIONALS_MISSING = {
    **SOAP_NOTE,
    "vitals": {
        "temperature_c": "36.8",
        "spo2_pct": "98",
        "bp_systolic": "122",
        "bp_diastolic": "78",
        "pulse_rate": "72",
        "pain_score": "2",
        "resp_rate": "16",
    },
    "measurements": {
        "weight_kg": "71.4",
        "height_cm": "168",
        "note": "Weight taken after shoes removed; patient reports recent appetite loss.",
    },
}
