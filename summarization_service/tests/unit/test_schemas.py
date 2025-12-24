"""Unit tests for Pydantic schemas."""
import pytest
from pydantic import ValidationError
from app.models.schemas import PatientDataInput, SummaryRequest, SummaryResponse


class TestPatientDataInput:
    """Test PatientDataInput schema validation."""
    
    def test_valid_minimal_data(self):
        """Test valid minimal patient data."""
        data = PatientDataInput(
            Age="45 years",
            Gender="Male",
            Diagnosis="Type 2 Diabetes"
        )
        assert data.Age == "45 years"
        assert data.Gender == "Male"
        assert data.Diagnosis == "Type 2 Diabetes"
        assert data.Symptoms == []
        assert data.Medications == []
    
    def test_valid_complete_data(self):
        """Test valid complete patient data."""
        data = PatientDataInput(
            Age="58 years",
            Gender="Male",
            Diagnosis="STEMI",
            Symptoms=["Chest pain", "SOB"],
            Medications=["Aspirin 325mg"],
            Allergies=["Penicillin"],
            Vitals={"BP": "140/90", "HR": "72"}
        )
        assert len(data.Symptoms) == 2
        assert len(data.Medications) == 1
        assert data.Vitals["BP"] == "140/90"
    
    def test_age_required(self):
        """Test that Age is required."""
        with pytest.raises(ValidationError):
            PatientDataInput(
                Gender="Male",
                Diagnosis="Diabetes"
            )
    
    def test_age_cannot_be_empty(self):
        """Test that Age cannot be empty."""
        with pytest.raises(ValidationError, match="Age cannot be empty"):
            PatientDataInput(
                Age="",
                Gender="Male",
                Diagnosis="Diabetes"
            )
    
    def test_gender_required(self):
        """Test that Gender is required."""
        with pytest.raises(ValidationError):
            PatientDataInput(
                Age="45 years",
                Diagnosis="Diabetes"
            )
    
    def test_gender_cannot_be_empty(self):
        """Test that Gender cannot be empty."""
        with pytest.raises(ValidationError, match="Gender cannot be empty"):
            PatientDataInput(
                Age="45 years",
                Gender="",
                Diagnosis="Diabetes"
            )
    
    def test_diagnosis_required(self):
        """Test that Diagnosis is required."""
        with pytest.raises(ValidationError):
            PatientDataInput(
                Age="45 years",
                Gender="Male"
            )
    
    def test_diagnosis_cannot_be_empty(self):
        """Test that Diagnosis cannot be empty."""
        with pytest.raises(ValidationError, match="Diagnosis cannot be empty"):
            PatientDataInput(
                Age="45 years",
                Gender="Male",
                Diagnosis=""
            )
    
    def test_optional_fields_default_to_empty(self):
        """Test that optional fields default to empty collections."""
        data = PatientDataInput(
            Age="45 years",
            Gender="Male",
            Diagnosis="Diabetes"
        )
        assert data.Symptoms == []
        assert data.Medications == []
        assert data.Surgeries == []
        assert data.Allergies == []
        assert data.Medical_Warnings == []
        assert data.Problems == []
        assert data.Vitals == {}
    
    def test_age_whitespace_trimmed(self):
        """Test that Age whitespace is trimmed."""
        data = PatientDataInput(
            Age="  45 years  ",
            Gender="Male",
            Diagnosis="Diabetes"
        )
        assert data.Age == "45 years"


class TestSummaryRequest:
    """Test SummaryRequest schema."""
    
    def test_valid_request_with_id(self):
        """Test valid request with request_id."""
        request = SummaryRequest(
            request_id="test-123",
            patient_data=PatientDataInput(
                Age="45 years",
                Gender="Male",
                Diagnosis="Diabetes"
            )
        )
        assert request.request_id == "test-123"
        assert request.patient_data.Age == "45 years"
    
    def test_valid_request_without_id(self):
        """Test valid request without request_id."""
        request = SummaryRequest(
            patient_data=PatientDataInput(
                Age="45 years",
                Gender="Male",
                Diagnosis="Diabetes"
            )
        )
        assert request.request_id is None
        assert request.patient_data is not None
    
    def test_patient_data_required(self):
        """Test that patient_data is required."""
        with pytest.raises(ValidationError):
            SummaryRequest(request_id="test-123")


class TestSummaryResponse:
    """Test SummaryResponse schema."""
    
    def test_valid_response(self):
        """Test valid response."""
        response = SummaryResponse(
            request_id="test-123",
            ClinicalSummary="A 45-year-old male with Type 2 Diabetes."
        )
        assert response.request_id == "test-123"
        assert "Diabetes" in response.ClinicalSummary
        assert response.processing_metadata == {}
    
    def test_response_with_metadata(self):
        """Test response with processing metadata."""
        metadata = {"model": "gpt-4o", "tokens": 250}
        response = SummaryResponse(
            ClinicalSummary="Test summary",
            processing_metadata=metadata
        )
        assert response.processing_metadata["model"] == "gpt-4o"
        assert response.processing_metadata["tokens"] == 250
    
    def test_clinical_summary_required(self):
        """Test that ClinicalSummary is required."""
        with pytest.raises(ValidationError):
            SummaryResponse(request_id="test-123")

