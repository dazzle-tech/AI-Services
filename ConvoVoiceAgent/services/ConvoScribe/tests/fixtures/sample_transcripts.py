"""Sample transcripts for unit tests."""

TWO_SPEAKER_NORMAL = [
    {"speaker_label": "SPEAKER_00", "start_time": 0.0, "end_time": 4.0, "text": "What brings you in today?"},
    {"speaker_label": "SPEAKER_01", "start_time": 4.5, "end_time": 9.0, "text": "I've had chest tightness since yesterday."},
    {"speaker_label": "SPEAKER_00", "start_time": 9.5, "end_time": 14.0, "text": "Any shortness of breath? I'll listen to your lungs."},
    {"speaker_label": "SPEAKER_01", "start_time": 14.5, "end_time": 18.0, "text": "A little when I walk upstairs."},
]

THREE_SPEAKER_WITH_FAMILY = [
    {"speaker_label": "SPEAKER_00", "start_time": 0.0, "end_time": 3.0, "text": "Hello, how can I help today?"},
    {"speaker_label": "SPEAKER_01", "start_time": 3.5, "end_time": 8.0, "text": "My mother has been dizzy all week."},
    {"speaker_label": "SPEAKER_02", "start_time": 8.5, "end_time": 12.0, "text": "Yes, and I feel nauseous in the mornings."},
    {"speaker_label": "SPEAKER_00", "start_time": 12.5, "end_time": 17.0, "text": "I'll check her blood pressure and review her medications."},
]

AMBIGUOUS_FEW_QUESTIONS = [
    {"speaker_label": "SPEAKER_00", "start_time": 0.0, "end_time": 5.0, "text": "The weather has been nice lately."},
    {"speaker_label": "SPEAKER_01", "start_time": 5.5, "end_time": 10.0, "text": "I've been feeling tired."},
    {"speaker_label": "SPEAKER_00", "start_time": 10.5, "end_time": 14.0, "text": "Okay, noted."},
]

SUMMARIZATION_SEGMENTS = [
    {"speaker_label": "SPEAKER_00", "start_time": 0.0, "end_time": 4.0, "text": "What symptoms are you having?"},
    {"speaker_label": "SPEAKER_01", "start_time": 4.5, "end_time": 9.0, "text": "Headache for two days."},
]

SUMMARIZATION_ROLE_MAP = {"SPEAKER_00": "doctor", "SPEAKER_01": "patient"}
