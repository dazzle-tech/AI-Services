"""Schema coercion for LLM unit-suffixed / empty numeric values."""

from app.models.window_schemas import AnesthesiaPreEvaluationPlanFields


def test_pre_eval_coerces_vital_sign_units_and_empty_gcs():
    payload = {
        "vitalSigns": {
            "weightKg": "82 kg",
            "bpSystolic": "128",
            "bpDiastolic": "82 mmHg",
            "pulseRate": "76 bpm",
            "tempC": "36.8 C",
            "spo2": "98%",
        },
        "clinicalExamination": {
            "cardiovascular": "Normal",
            "gcs": "",
        },
    }
    parsed = AnesthesiaPreEvaluationPlanFields.model_validate(payload)
    assert parsed.vitalSigns is not None
    assert parsed.vitalSigns.weightKg == 82.0
    assert parsed.vitalSigns.bpSystolic == 128
    assert parsed.vitalSigns.bpDiastolic == 82
    assert parsed.vitalSigns.pulseRate == 76
    assert parsed.vitalSigns.tempC == 36.8
    assert parsed.vitalSigns.spo2 == 98
    assert parsed.clinicalExamination is not None
    assert parsed.clinicalExamination.gcs is None
