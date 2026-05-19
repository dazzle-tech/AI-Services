"""Unit tests for Pydantic schemas."""
import pytest
from pydantic import ValidationError
from app.models.schemas import (
    PatientContext,
    ClinicalData,
    OperationalData,
    DischargePlanningRequest,
    DischargePlan,
    DischargeBlocker,
    DischargePlanningResponse,
    VitalReading,
)
from tests.fixtures.sample_data import (
    SAMPLE_REQUEST_MINIMAL,
    SAMPLE_REQUEST_FULL,
)


class TestPatientContext:
    """Test PatientContext schema."""
    
    def test_valid_minimal(self):
        """Test valid minimal patient context."""
        ctx = PatientContext(patient_id="P-001", primary_diagnosis="Pneumonia")
        assert ctx.patient_id == "P-001"
        assert ctx.primary_diagnosis == "Pneumonia"
        assert ctx.secondary_diagnoses == []
    
    def test_valid_full(self):
        """Test valid full patient context."""
        ctx = PatientContext(
            patient_id="P-001",
            admission_date="2026-03-10",
            primary_diagnosis="Pneumonia",
            secondary_diagnoses=["Diabetes"],
            current_status="improving",
        )
        assert ctx.secondary_diagnoses == ["Diabetes"]
        assert ctx.current_status == "improving"
    
    def test_patient_id_required(self):
        """Test patient_id is required."""
        with pytest.raises(ValidationError):
            PatientContext(primary_diagnosis="Pneumonia")
    
    def test_primary_diagnosis_required(self):
        """Test primary_diagnosis is required."""
        with pytest.raises(ValidationError):
            PatientContext(patient_id="P-001")


class TestDischargePlanningRequest:
    """Test DischargePlanningRequest schema."""
    
    def test_valid_minimal_request(self):
        """Test valid minimal request."""
        req = DischargePlanningRequest(
            request_id="test-001",
            patient_context=PatientContext(patient_id="P-1", primary_diagnosis="Diabetes"),
            clinical_data=ClinicalData(),
            operational_data=OperationalData(),
        )
        assert req.request_id == "test-001"
        assert req.patient_context.patient_id == "P-1"
    
    def test_valid_full_request(self):
        """Test valid full request."""
        req = SAMPLE_REQUEST_FULL
        assert req.patient_context.secondary_diagnoses
        assert req.clinical_data.medications_current
        assert req.operational_data.equipment_needs
    
    def test_patient_context_required(self):
        """Test patient_context is required."""
        with pytest.raises(ValidationError):
            DischargePlanningRequest(
                clinical_data=ClinicalData(),
                operational_data=OperationalData(),
            )
    
    def test_clinical_data_required(self):
        """Test clinical_data is required."""
        with pytest.raises(ValidationError):
            DischargePlanningRequest(
                patient_context=PatientContext(patient_id="P-1", primary_diagnosis="Dx"),
                operational_data=OperationalData(),
            )
    
    def test_operational_data_required(self):
        """Test operational_data is required."""
        with pytest.raises(ValidationError):
            DischargePlanningRequest(
                patient_context=PatientContext(patient_id="P-1", primary_diagnosis="Dx"),
                clinical_data=ClinicalData(),
            )


class TestDischargePlan:
    """Test DischargePlan schema."""
    
    def test_valid_discharge_plan(self):
        """Test valid discharge plan."""
        plan = DischargePlan(
            readiness_status="needs_review",
            readiness_reason="Unresolved blockers remain.",
            blockers=[
                DischargeBlocker(category="pending_test", title="Blood culture pending", reason="Test not complete"),
            ],
            medication_reconciliation_concerns=["Verify Prednisone"],
            follow_up_considerations=["Schedule pulmonology"],
            draft_discharge_summary="Patient admitted with pneumonia.",
            disclaimer="This output supports discharge planning and does not replace clinician judgment.",
        )
        assert plan.readiness_status == "needs_review"
        assert len(plan.blockers) == 1
        assert plan.blockers[0].category == "pending_test"


class TestDischargePlanningResponse:
    """Test DischargePlanningResponse schema."""
    
    def test_valid_response(self):
        """Test valid response."""
        plan = DischargePlan(
            readiness_status="ready",
            readiness_reason="All criteria met.",
            blockers=[],
            medication_reconciliation_concerns=[],
            follow_up_considerations=[],
            draft_discharge_summary="Summary text.",
            disclaimer="This output supports discharge planning.",
        )
        resp = DischargePlanningResponse(
            request_id="req-1",
            discharge_plan=plan,
            summary="Assessment generated.",
        )
        assert resp.request_id == "req-1"
        assert resp.discharge_plan.readiness_status == "ready"
        assert "discharge_plan" in resp.model_dump()
