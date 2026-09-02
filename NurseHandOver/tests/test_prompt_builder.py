"""
test_prompt_builder.py
----------------------
Tests for prompt_builder.py — no API calls made here.
Validates that prompts are correctly assembled from patient data.
"""

import pytest
from app.services.prompt_builder import get_system_prompt, build_user_prompt


class TestSystemPrompt:
    def test_returns_string(self):
        prompt = get_system_prompt()
        assert isinstance(prompt, str)

    def test_contains_sbar_sections(self):
        prompt = get_system_prompt()
        for section in ["Situation", "Background", "Assessment", "Recommendation"]:
            assert section in prompt, f"System prompt missing SBAR section: {section}"

    def test_contains_priority_levels(self):
        prompt = get_system_prompt()
        for level in ["critical", "watch", "stable"]:
            assert level in prompt.lower(), f"System prompt missing priority level: {level}"

    def test_contains_json_output_instruction(self):
        prompt = get_system_prompt()
        assert "json" in prompt.lower()
        assert "patient_id" in prompt

    def test_contains_hallucination_guard(self):
        """Ensures the no-inference rule is present."""
        prompt = get_system_prompt()
        assert "never infer" in prompt.lower() or "never assume" in prompt.lower()

    def test_contains_vital_thresholds(self):
        """Priority classification thresholds must be in the system prompt."""
        prompt = get_system_prompt()
        assert "92" in prompt   # SpO2 threshold
        assert "38.5" in prompt # Temperature threshold


class TestUserPrompt:
    def test_contains_patient_id(self, critical_patient):
        prompt = build_user_prompt(critical_patient)
        assert critical_patient.patient_id in prompt

    def test_contains_patient_name(self, critical_patient):
        prompt = build_user_prompt(critical_patient)
        assert critical_patient.name in prompt

    def test_contains_all_vitals(self, critical_patient):
        prompt = build_user_prompt(critical_patient)
        v = critical_patient.vitals
        assert str(v.hr)   in prompt
        assert str(v.temp) in prompt
        assert str(v.spo2) in prompt
        assert str(v.rr)   in prompt
        assert v.bp        in prompt

    def test_contains_all_medications(self, critical_patient):
        prompt = build_user_prompt(critical_patient)
        for med in critical_patient.medications:
            assert med.name in prompt
            assert med.status in prompt

    def test_contains_pending_orders(self, critical_patient):
        prompt = build_user_prompt(critical_patient)
        for order in critical_patient.pending_orders:
            assert order in prompt

    def test_contains_alerts(self, critical_patient):
        prompt = build_user_prompt(critical_patient)
        for alert in critical_patient.alerts:
            assert alert in prompt

    def test_contains_nurse_notes(self, critical_patient):
        prompt = build_user_prompt(critical_patient)
        for note in critical_patient.nurse_notes:
            assert note.time in prompt
            assert note.text in prompt

    def test_no_medications_handled_gracefully(self, stable_patient):
        """A patient with no alerts or notes should not break prompt building."""
        stable_patient.alerts = []
        stable_patient.nurse_notes = []
        prompt = build_user_prompt(stable_patient)
        assert "None" in prompt  # graceful empty state message

    def test_prompt_is_non_empty_string(self, watch_patient):
        prompt = build_user_prompt(watch_patient)
        assert isinstance(prompt, str)
        assert len(prompt) > 200  # sanity check — must be a substantive prompt

    def test_includes_current_status_fields(self, critical_patient):
        prompt = build_user_prompt(critical_patient)
        assert "Community-acquired pneumonia" in prompt
        assert "COPD, type 2 diabetes" in prompt
        assert "Hospital Course" in prompt
        assert "Handover generated at:" in prompt
        assert "Penicillin" in prompt
        assert "Fall risk" in prompt
        assert "Repeat chest X-ray" in prompt

    def test_excludes_resolved_allergies_and_warnings(self, critical_patient):
        prompt = build_user_prompt(critical_patient)
        assert "Seasonal pollen" not in prompt
        assert "Isolation discontinued" not in prompt
        assert "Prior bronchoscopy" not in prompt

    def test_includes_latest_vital_history_only(self):
        from app.models.schemas import Patient, VitalSignReading

        patient = Patient(
            patient_id="pt_v",
            name="Vital Case",
            vital_signs=[
                VitalSignReading(type="hr", value=70, recorded_at="2026-09-01T08:00:00+00:00"),
                VitalSignReading(type="hr", value=110, recorded_at="2026-09-02T14:00:00+00:00"),
            ],
        )
        prompt = build_user_prompt(patient)
        assert "110" in prompt
        assert "  Heart Rate        : 110 bpm" in prompt
