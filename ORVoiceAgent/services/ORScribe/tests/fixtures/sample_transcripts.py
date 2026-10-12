"""Sample OR transcripts for unit tests."""

THREE_ROLE_STANDARD = [
    {"speaker_label": "SPEAKER_00", "start_time": 0.0, "end_time": 8.0, "text": "Sign in complete. Patient identity confirmed, site marked."},
    {"speaker_label": "SPEAKER_01", "start_time": 8.5, "end_time": 15.0, "text": "Anesthesia plan reviewed. Allergies noted. Consent verified."},
    {"speaker_label": "SPEAKER_02", "start_time": 15.5, "end_time": 22.0, "text": "Time out. Team introductions. Anticipated critical events reviewed."},
    {"speaker_label": "SPEAKER_00", "start_time": 22.5, "end_time": 28.0, "text": "Making incision now. Scalpel."},
    {"speaker_label": "SPEAKER_01", "start_time": 28.5, "end_time": 35.0, "text": "Blood pressure 120 over 80. Heart rate 72. Giving propofol 100 milligrams."},
    {"speaker_label": "SPEAKER_02", "start_time": 35.5, "end_time": 42.0, "text": "Sponge count correct. Instrument count correct."},
    {"speaker_label": "SPEAKER_00", "start_time": 872.0, "end_time": 880.0, "text": "Sign out. Procedure recorded as laparoscopic cholecystectomy. Specimen labeled."},
]

FOUR_SPEAKER_WITH_RESIDENT = [
    {"speaker_label": "SPEAKER_00", "start_time": 0.0, "end_time": 6.0, "text": "Sign in. Patient identity confirmed."},
    {"speaker_label": "SPEAKER_01", "start_time": 6.5, "end_time": 12.0, "text": "Anesthesia plan reviewed. Vitals stable."},
    {"speaker_label": "SPEAKER_02", "start_time": 12.5, "end_time": 18.0, "text": "Time out. Instrument count verified."},
    {"speaker_label": "SPEAKER_00", "start_time": 18.5, "end_time": 24.0, "text": "Making incision."},
    {"speaker_label": "SPEAKER_03", "start_time": 24.5, "end_time": 30.0, "text": "Retractor please. Holding retraction."},
    {"speaker_label": "SPEAKER_02", "start_time": 30.5, "end_time": 36.0, "text": "Sponge count correct."},
]

AMBIGUOUS_LOW_CONFIDENCE = [
    {"speaker_label": "SPEAKER_00", "start_time": 0.0, "end_time": 5.0, "text": "Ready when you are."},
    {"speaker_label": "SPEAKER_01", "start_time": 5.5, "end_time": 10.0, "text": "Same here."},
    {"speaker_label": "SPEAKER_02", "start_time": 10.5, "end_time": 15.0, "text": "Proceeding."},
]

CHECKLIST_INCOMPLETE = [
    {"speaker_label": "SPEAKER_00", "start_time": 0.0, "end_time": 8.0, "text": "Sign in. Patient identity confirmed."},
    {"speaker_label": "SPEAKER_00", "start_time": 8.5, "end_time": 15.0, "text": "Making incision now."},
    {"speaker_label": "SPEAKER_02", "start_time": 15.5, "end_time": 22.0, "text": "Sponge count correct."},
]

MEDICATION_NO_DOSE = [
    {"speaker_label": "SPEAKER_01", "start_time": 0.0, "end_time": 8.0, "text": "Administering medication now."},
    {"speaker_label": "SPEAKER_01", "start_time": 8.5, "end_time": 15.0, "text": "Blood pressure stable."},
]

MEDICATION_WITH_DOSE = [
    {"speaker_label": "SPEAKER_01", "start_time": 0.0, "end_time": 8.0, "text": "Giving propofol 100 milligrams."},
]

COUNT_AMBIGUOUS = [
    {"speaker_label": "SPEAKER_02", "start_time": 0.0, "end_time": 8.0, "text": "Checking the count now."},
]
