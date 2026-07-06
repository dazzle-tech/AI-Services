"""Unit tests for Pydantic schemas."""
import os

import pytest
from pydantic import ValidationError

from app.models.schemas import Alert, AlertRequest, AlertResponse, PatientRecordInput

TEST_MODEL = os.getenv("OPENAI_MODEL", "")


class TestPatientRecordInput:
    """Test PatientRecordInput schema validation."""

    def test_valid_minimal_data(self):
        """Test valid minimal patient data."""
        data = PatientRecordInput(
            patient_id="P-1001",
            demographics={"age": 58, "sex": "male"},
        )
        assert data.patient_id == "P-1001"
        assert data.demographics.age == 58
        assert data.demographics.sex == "male"
        assert data.diagnoses == []

    def test_valid_complete_data(self):
        """Test valid complete patient data."""
        data = PatientRecordInput(
            patient_id="P-1001",
            demographics={"age": 58, "sex": "male"},
            medications=[{"name": "Lisinopril", "status": "active"}],
            lab_results=[{"name": "Creatinine", "value": "1.8", "unit": "mg/dL"}],
        )
        assert len(data.medications) == 1
        assert data.medications[0].name == "Lisinopril"
        assert data.lab_results[0].value == "1.8"

    def test_patient_id_required(self):
        """Test that patient_id is required."""
        with pytest.raises(ValidationError):
            PatientRecordInput()

    def test_patient_id_cannot_be_empty(self):
        """Test that patient_id cannot be empty."""
        with pytest.raises(ValidationError, match="patient_id cannot be empty"):
            PatientRecordInput(patient_id="  ")

    def test_optional_fields_default_to_empty(self):
        """Test that optional fields default to empty collections."""
        data = PatientRecordInput(patient_id="P-1001")
        assert data.diagnoses == []
        assert data.medications == []
        assert data.lab_results == []
        assert data.historical_lab_results == []
        assert data.vitals == []
        assert data.notes == []
        assert data.problem_list == []
        assert data.discharge_follow_up == []

    def test_problem_list_normalization(self):
        """Test problem list normalization trims empty strings."""
        data = PatientRecordInput(
            patient_id="P-1001",
            problem_list=[" Acute kidney injury ", "", "Chest pain"],
        )
        assert data.problem_list == ["Acute kidney injury", "Chest pain"]


class TestAlertRequest:
    """Test AlertRequest schema."""

    def test_valid_request_with_id(self):
        """Test valid request with request_id."""
        request = AlertRequest(
            request_id="test-123",
            patient_record=PatientRecordInput(patient_id="P-1001"),
        )
        assert request.request_id == "test-123"
        assert request.patient_record.patient_id == "P-1001"

    def test_valid_request_without_id(self):
        """Test valid request without request_id."""
        request = AlertRequest(patient_record=PatientRecordInput(patient_id="P-1001"))
        assert request.request_id is None
        assert request.patient_record is not None

    def test_patient_record_required(self):
        """Test that patient_record is required."""
        with pytest.raises(ValidationError):
            AlertRequest(request_id="test-123")


class TestAlertResponse:
    """Test Alert and AlertResponse schemas."""

    def test_valid_alert(self):
        """Test valid alert."""
        alert = Alert(
            alert_id="ALT-001",
            category="specialist_consult",
            severity="high",
            title="Consider neurology consultation",
            reason="Imaging report describes a possible intracranial hemorrhage.",
            recommended_specialty="Neurology",
            supporting_evidence=["CT Head report mentions possible intracranial hemorrhage"],
            suggested_action="Review imaging urgently and determine whether neurology input is needed.",
            confidence="high",
        )
        assert alert.category == "specialist_consult"
        assert alert.severity == "high"
        assert len(alert.supporting_evidence) == 1

    def test_alert_normalizes_category(self):
        """Test alert category normalization."""
        alert = Alert(
            alert_id="ALT-001",
            category="specialist consult",
            severity="HIGH",
            title="Consider nephrology consultation",
            reason="Creatinine increased across serial results.",
            recommended_specialty="Nephrology",
            supporting_evidence=["Creatinine 1.0 on 2026-03-14", "Creatinine 1.8 on 2026-03-16"],
            suggested_action="Review renal trend and determine whether nephrology consultation is needed.",
            confidence="Medium",
        )
        assert alert.category == "specialist_consult"
        assert alert.severity == "high"
        assert alert.confidence == "medium"

    def test_response_with_metadata(self):
        """Test response with metadata."""
        response = AlertResponse(
            request_id="test-123",
            alerts=[],
            summary="No clinically meaningful alerts were identified from the provided record.",
            processing_metadata={"model": TEST_MODEL, "alert_count": 0},
        )
        assert response.processing_metadata["model"] == TEST_MODEL
        assert response.processing_metadata["alert_count"] == 0

    def test_summary_required(self):
        """Test that summary is required."""
        with pytest.raises(ValidationError):
            AlertResponse(request_id="test-123", alerts=[])
