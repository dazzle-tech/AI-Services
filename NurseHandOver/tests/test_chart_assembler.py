"""Tests for chart_assembler — allergy/warning filters, latest vitals, pending procedures."""

from datetime import datetime, timezone

from app.models.schemas import (
    Allergy,
    ClinicalWarning,
    Patient,
    PendingProcedure,
    VitalSignReading,
    Vitals,
)
from app.services.chart_assembler import assemble_current_status


def _patient(**overrides) -> Patient:
    data = dict(
        patient_id="pt_001",
        name="Margaret O'Brien",
        diagnosis="Community-acquired pneumonia",
        past_medical_history="COPD, hypertension",
        hospital_course="Admitted with hypoxia; started on IV antibiotics.",
    )
    data.update(overrides)
    return Patient(**data)


class TestAllergyFilter:
    def test_drops_resolved_allergies(self):
        patient = _patient(
            allergies=[
                Allergy(name="Penicillin", status="not resolved"),
                Allergy(name="Latex", status="resolved"),
                Allergy(name="Peanuts", resolved=True),
                Allergy(name="Iodine"),
            ]
        )
        status = assemble_current_status(patient)
        names = [a.name for a in status.allergies]
        assert names == ["Penicillin", "Iodine"]

    def test_accepts_bare_allergy_strings(self):
        patient = Patient.model_validate(
            {"patient_id": "pt_x", "name": "Test", "allergies": ["Morphine", "Codeine"]}
        )
        status = assemble_current_status(patient)
        assert [a.name for a in status.allergies] == ["Morphine", "Codeine"]


class TestWarningFilter:
    def test_drops_resolved_warnings(self):
        patient = _patient(
            warnings=[
                ClinicalWarning(text="Fall risk", status="active"),
                ClinicalWarning(text="Isolation — cleared", status="resolved"),
                ClinicalWarning(text="NBM overnight", resolved=False),
            ]
        )
        status = assemble_current_status(patient)
        texts = [w.text for w in status.warnings]
        assert texts == ["Fall risk", "NBM overnight"]


class TestLatestVitals:
    def test_keeps_latest_reading_per_type(self):
        patient = _patient(
            vital_signs=[
                VitalSignReading(type="hr", value=90, unit="bpm", recorded_at="2026-09-02T08:00:00+00:00"),
                VitalSignReading(type="heart_rate", value=108, unit="bpm", recorded_at="2026-09-02T14:45:00+00:00"),
                VitalSignReading(type="spo2", value=96, unit="%", recorded_at="2026-09-02T08:00:00+00:00"),
                VitalSignReading(type="SpO2", value=91, unit="%", recorded_at="2026-09-02T14:30:00+00:00"),
                VitalSignReading(type="temp", value=37.2, unit="°C", recorded_at="2026-09-02T08:00:00+00:00"),
            ]
        )
        status = assemble_current_status(patient)
        by_type = {v.type: v for v in status.vital_signs}
        assert by_type["hr"].value == 108
        assert by_type["spo2"].value == 91
        assert by_type["temp"].value == 37.2
        assert len(status.vital_signs) == 3

    def test_falls_back_to_compact_vitals(self):
        patient = _patient(
            vitals=Vitals(hr=72, bp="120/80", temp=36.8, rr=16, spo2=98, last_updated="13:30"),
        )
        status = assemble_current_status(patient)
        by_type = {v.type: v for v in status.vital_signs}
        assert by_type["hr"].value == 72
        assert by_type["bp"].value == "120/80"
        assert by_type["hr"].recorded_at == "13:30"


class TestPendingProcedures:
    def test_drops_completed_keeps_pending(self):
        patient = _patient(
            pending_procedures=[
                PendingProcedure(name="Chest X-ray", status="pending"),
                PendingProcedure(name="Appendectomy", status="completed"),
                PendingProcedure(name="Bronchoscopy", status="scheduled", scheduled_at="2026-09-03T09:00:00Z"),
                PendingProcedure(name="Cancelled MRI", status="cancelled"),
            ]
        )
        status = assemble_current_status(patient)
        names = [p.name for p in status.pending_procedures]
        assert names == ["Chest X-ray", "Bronchoscopy"]


class TestCurrentStatusSnapshot:
    def test_copies_clinical_text_and_stamps_generated_at(self):
        stamp = datetime(2026, 9, 2, 8, 0, tzinfo=timezone.utc)
        patient = _patient()
        status = assemble_current_status(patient, generated_at=stamp)
        assert status.diagnosis == "Community-acquired pneumonia"
        assert status.past_medical_history == "COPD, hypertension"
        assert "IV antibiotics" in status.hospital_course
        assert status.generated_at == stamp
        assert status.patient_id == "pt_001"
