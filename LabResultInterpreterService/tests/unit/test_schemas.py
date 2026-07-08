"""Unit tests for Pydantic schemas."""
import pytest
from pydantic import ValidationError
from app.models.schemas import (
    LabResultItem,
    PatientContext,
    LabInterpretationRequest,
    LabInterpretationResponse,
    LabInterpretation,
    LabPattern,
    LabTrend,
)


class TestLabResultItem:
    """Test LabResultItem schema."""

    def test_valid_lab_item(self):
        """Test valid lab result item."""
        lab = LabResultItem(
            name="WBC",
            value="10.5",
            unit="10^9/L",
            reference_range="4.0-11.0",
            flag="normal",
        )
        assert lab.name == "WBC"
        assert lab.value == "10.5"
        assert lab.unit == "10^9/L"

    def test_minimal_lab_item(self):
        """Test lab item with required fields only."""
        lab = LabResultItem(name="CRP", value="5.2")
        assert lab.name == "CRP"
        assert lab.value == "5.2"
        assert lab.unit is None
        assert lab.flag is None


class TestPatientContext:
    """Test PatientContext schema."""

    def test_valid_context(self):
        """Test valid patient context."""
        ctx = PatientContext(
            patient_id="P-001",
            age=45,
            sex="male",
            known_conditions=["Diabetes"],
            medications=["Metformin"],
        )
        assert ctx.patient_id == "P-001"
        assert ctx.age == 45
        assert len(ctx.known_conditions) == 1

    def test_empty_context(self):
        """Test optional patient context defaults."""
        ctx = PatientContext()
        assert ctx.patient_id is None
        assert ctx.known_conditions == []
        assert ctx.medications == []

    def test_context_accepts_string_age_and_medication_objects(self):
        """Test patient context accepts string age values and medication objects."""
        ctx = PatientContext(
            age="10 Years 9 Months 7 Days",
            sex="FEMALE",
            known_conditions=[],
            medications=[
                {
                    "name": "nexium",
                    "start_date": "2026-07-07T21:00:00.000Z",
                    "end_date": None,
                }
            ],
        )
        assert ctx.age == "10 Years 9 Months 7 Days"
        assert ctx.sex == "FEMALE"
        assert len(ctx.medications) == 1
        assert ctx.medications[0]["name"] == "nexium"


class TestLabInterpretationRequest:
    """Test LabInterpretationRequest schema."""

    def test_valid_request_minimal(self):
        """Test valid request with minimal labs."""
        req = LabInterpretationRequest(
            request_id="req-001",
            lab_results=[
                LabResultItem(name="WBC", value="10.0"),
            ],
        )
        assert req.request_id == "req-001"
        assert len(req.lab_results) == 1
        assert req.patient_context is None
        assert req.historical_lab_results == []

    def test_valid_request_full(self):
        """Test valid request with all fields."""
        req = LabInterpretationRequest(
            request_id="req-002",
            patient_context=PatientContext(patient_id="P-001", age=58),
            lab_results=[
                LabResultItem(name="WBC", value="18.2", flag="high"),
            ],
            historical_lab_results=[
                LabResultItem(name="Creatinine", value="1.0"),
                LabResultItem(name="Creatinine", value="1.8"),
            ],
        )
        assert len(req.lab_results) == 1
        assert len(req.historical_lab_results) == 2

    def test_request_accepts_top_level_medications(self):
        """Test that top-level medications are accepted and copied into patient context."""
        req = LabInterpretationRequest(
            request_id="req-004",
            medications=[
                {
                    "name": "nexium",
                    "start_date": "2026-07-07T21:00:00.000Z",
                    "end_date": None,
                }
            ],
            lab_results=[LabResultItem(name="CBC1", value="4.00")],
        )
        assert req.patient_context is not None
        assert req.patient_context.medications[0]["name"] == "nexium"

    def test_lab_results_required(self):
        """Test that lab_results is required and cannot be empty."""
        with pytest.raises(ValidationError):
            LabInterpretationRequest(lab_results=[])

    def test_lab_results_cannot_be_empty(self):
        """Test that empty lab_results list fails."""
        with pytest.raises(ValidationError, match="At least one lab result"):
            LabInterpretationRequest(
                request_id="req-003",
                lab_results=[],
            )


class TestLabInterpretationResponse:
    """Test LabInterpretationResponse schema."""

    def test_valid_response(self):
        """Test valid response."""
        interpretation = LabInterpretation(
            severity="high",
            key_findings=["WBC elevated", "CRP elevated"],
            patterns=[
                LabPattern(label="possible_infection", reason="WBC and CRP suggest infection"),
            ],
            trends=[
                LabTrend(lab_name="Creatinine", direction="rising", summary="Increased from 1.0 to 1.8"),
            ],
            follow_up_considerations=["Repeat labs in 24h"],
            disclaimer="This output is interpretation support and not a diagnosis.",
        )
        response = LabInterpretationResponse(
            request_id="req-001",
            interpretation=interpretation,
            summary="Lab interpretation generated successfully.",
        )
        assert response.request_id == "req-001"
        assert response.interpretation.severity == "high"
        assert len(response.interpretation.key_findings) == 2
        assert "interpretation support" in response.interpretation.disclaimer
