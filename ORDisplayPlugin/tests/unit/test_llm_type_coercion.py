"""Cross-window LLM type coercion on all window schemas."""

from app.models.window_schemas import (
    AnesthesiaInductionIntraoperativeFields,
    AnesthesiaObservationDrugsFields,
    AnesthesiaPreEvaluationPlanFields,
    NursingIntraoperativeFields,
    NursingSignOutFields,
    NursingTimeOutFields,
    NursingVerificationOfMarkingSiteFields,
    OperativeNoteFields,
    WINDOW_SCHEMAS,
)


def test_intraoperative_coerces_numeric_string_fields():
    parsed = NursingIntraoperativeFields.model_validate(
        {
            "operationStaff": {"room": 1, "scrubNurse1": 42},
            "foleyCatheter": {"catheterSize": "16 Fr", "urineOutputCc": "250 cc", "color": 3},
            "tourniquet": {"totalDurationMinutes": "75 min", "pressureMmHg": "300 mmHg"},
            "diathermiaAndLaser": {"electroRangeCutting": 30, "electroRangeCoagulation": 25},
            "laser": {"na": False, "pulseEnergy": 50, "frequency": 100, "laserFiber": 365},
            "drains": {"entries": [{"type": "HEMOVAC", "numberOfDrains": "2", "size": "28 Fr"}]},
            "specimens": {"entries": [{"type": "PATHOLOGY", "numberOfSamples": "2"}]},
        }
    )
    assert parsed.operationStaff.room == "1"
    assert parsed.foleyCatheter.catheterSize == 16
    assert parsed.foleyCatheter.urineOutputCc == 250
    assert parsed.foleyCatheter.color == "3"
    assert parsed.tourniquet.totalDurationMinutes == 75
    assert parsed.tourniquet.pressureMmHg == 300
    assert parsed.diathermiaAndLaser.electroRangeCutting == "30"
    assert parsed.laser.pulseEnergy == "50"
    assert parsed.laser.frequency == "100"
    assert parsed.drains.entries[0].numberOfDrains == 2
    assert parsed.drains.entries[0].size == 28
    assert parsed.specimens.entries[0].numberOfSamples == 2


def test_pre_eval_and_induction_and_observation_and_note():
    pre = AnesthesiaPreEvaluationPlanFields.model_validate(
        {
            "vitalSigns": {"weightKg": "82 kg", "tempC": "36.8 C", "spo2": "98%"},
            "clinicalExamination": {"gcs": "", "cardiovascular": None},
            "asa": {"asaClass": 2, "emergency": "yes"},
        }
    )
    assert pre.vitalSigns.weightKg == 82.0
    assert pre.vitalSigns.tempC == 36.8
    assert pre.vitalSigns.spo2 == 98
    assert pre.clinicalExamination.gcs is None
    assert pre.clinicalExamination.cardiovascular == ""
    assert pre.asa.asaClass == "2"
    assert pre.asa.emergency is True

    induction = AnesthesiaInductionIntraoperativeFields.model_validate(
        {
            "preInductionAssessment": {
                "bpSystolic": "120 mmHg",
                "hr": "",
                "npo": "yes",
            }
        }
    )
    assert induction.preInductionAssessment.bpSystolic == 120
    assert induction.preInductionAssessment.hr is None
    assert induction.preInductionAssessment.npo == "yes"

    obs = AnesthesiaObservationDrugsFields.model_validate(
        {
            "vitalSign": {"bpSystolic": "110", "tempC": 36.5, "tidalVolume": 500},
            "bloodLoss": {"bloodQuantity": 2, "bloodLoss": "150 ml"},
        }
    )
    assert obs.vitalSign.bpSystolic == 110
    assert obs.vitalSign.tempC == "36.5"
    assert obs.vitalSign.tidalVolume == "500"
    assert obs.bloodLoss.bloodQuantity == "2"
    assert obs.bloodLoss.bloodLoss == 150

    note = OperativeNoteFields.model_validate(
        {"estimatedBloodLossMl": "200 ml", "complication": None, "operationNote": 123}
    )
    assert note.estimatedBloodLossMl == 200
    assert note.complication is None
    assert note.operationNote == "123"


def test_checklist_windows_coerce_notes_and_ids():
    verification = NursingVerificationOfMarkingSiteFields.model_validate(
        {
            "checklist": [{"key": "site_side_level_documented", "label": "x", "checked": "true", "note": None}],
            "siteMarking": {"status": "MARKED", "note": None},
        }
    )
    assert verification.checklist[0].checked is True
    assert verification.checklist[0].note == ""
    assert verification.siteMarking.note == ""

    timeout = NursingTimeOutFields.model_validate(
        {"staff": {"surgeon": {"staffId": 2041, "displayName": "Omar"}, "nurse": {}}}
    )
    assert timeout.staff.surgeon.staffId == "2041"

    sign_out = NursingSignOutFields.model_validate(
        {
            "checklist": [
                {
                    "key": "address_any_equipment_problems",
                    "label": "x",
                    "checked": "no",
                    "response": 0,
                    "note": None,
                }
            ]
        }
    )
    assert sign_out.checklist[0].checked is False
    assert sign_out.checklist[0].response == "0"
    assert sign_out.checklist[0].note == ""


def test_every_window_schema_accepts_empty_object():
    for window_id, schema in WINDOW_SCHEMAS.items():
        parsed = schema.model_validate({})
        assert parsed is not None, window_id
