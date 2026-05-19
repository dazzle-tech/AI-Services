"""Unit tests for Pydantic schemas."""
import pytest
from pydantic import ValidationError
from app.models.schemas import (
    UnitContext,
    NurseContext,
    PatientInput,
    VitalReading,
    LabAlert,
    MedicationTask,
    NursingTask,
    Note,
    TaskPrioritizationRequest,
    TaskPrioritizationResponse,
    PrioritizedTask,
)


class TestUnitContext:
    """Test UnitContext schema."""

    def test_valid_unit_context(self):
        """Test valid unit context."""
        ctx = UnitContext(unit_name="Ward A", shift="day", generated_at="2026-03-16T09:00:00Z")
        assert ctx.unit_name == "Ward A"
        assert ctx.shift == "day"


class TestNurseContext:
    """Test NurseContext schema."""

    def test_valid_nurse_context(self):
        """Test valid nurse context."""
        ctx = NurseContext(nurse_id="N-204", assigned_rooms=["101", "102"])
        assert ctx.nurse_id == "N-204"
        assert len(ctx.assigned_rooms) == 2


class TestPatientInput:
    """Test PatientInput schema."""

    def test_valid_minimal_patient(self):
        """Test valid minimal patient."""
        p = PatientInput(patient_id="P-1", room="101")
        assert p.patient_id == "P-1"
        assert p.room == "101"
        assert p.vitals == []
        assert p.medication_tasks == []

    def test_valid_full_patient(self):
        """Test valid full patient."""
        p = PatientInput(
            patient_id="P-1",
            room="101",
            patient_risk_flags=["fall_risk"],
            vitals=[VitalReading(name="SpO2", value="88", unit="%", timestamp="2026-03-16T08:00:00Z")],
            medication_tasks=[MedicationTask(task_id="MED-1", medication_name="Insulin", due_time="2026-03-16T09:00:00Z")],
        )
        assert len(p.vitals) == 1
        assert len(p.medication_tasks) == 1

    def test_patient_id_required(self):
        """Test that patient_id is required."""
        with pytest.raises(ValidationError):
            PatientInput(room="101")

    def test_room_required(self):
        """Test that room is required."""
        with pytest.raises(ValidationError):
            PatientInput(patient_id="P-1")


class TestTaskPrioritizationRequest:
    """Test TaskPrioritizationRequest schema."""

    def test_valid_request_with_id(self):
        """Test valid request with request_id."""
        req = TaskPrioritizationRequest(
            request_id="req-001",
            unit_context=UnitContext(unit_name="Ward", shift="day", generated_at="2026-03-16T09:00:00Z"),
            nurse_context=NurseContext(nurse_id="N-1", assigned_rooms=["101"]),
            patients=[PatientInput(patient_id="P-1", room="101")]
        )
        assert req.request_id == "req-001"
        assert len(req.patients) == 1

    def test_valid_request_without_id(self):
        """Test valid request without request_id."""
        req = TaskPrioritizationRequest(
            unit_context=UnitContext(unit_name="Ward", shift="day", generated_at="2026-03-16T09:00:00Z"),
            nurse_context=NurseContext(nurse_id="N-1", assigned_rooms=[]),
            patients=[PatientInput(patient_id="P-1", room="101")]
        )
        assert req.request_id is None

    def test_unit_context_required(self):
        """Test that unit_context is required."""
        with pytest.raises(ValidationError):
            TaskPrioritizationRequest(
                nurse_context=NurseContext(nurse_id="N-1", assigned_rooms=[]),
                patients=[PatientInput(patient_id="P-1", room="101")]
            )

    def test_patients_required(self):
        """Test that patients is required."""
        with pytest.raises(ValidationError):
            TaskPrioritizationRequest(
                unit_context=UnitContext(unit_name="Ward", shift="day", generated_at="2026-03-16T09:00:00Z"),
                nurse_context=NurseContext(nurse_id="N-1", assigned_rooms=[])
            )


class TestTaskPrioritizationResponse:
    """Test TaskPrioritizationResponse schema."""

    def test_valid_response(self):
        """Test valid response."""
        resp = TaskPrioritizationResponse(
            request_id="req-001",
            prioritized_tasks=[
                PrioritizedTask(
                    rank=1,
                    patient_id="P-1",
                    room="101",
                    task_id="TASK-1",
                    task_type="clinical_reassessment",
                    title="Reassess oxygen",
                    reason="SpO2 low",
                    urgency="critical",
                    recommended_timeframe="immediate",
                    source_signals=["oxygen_saturation=88%"]
                )
            ],
            summary="Done",
        )
        assert resp.request_id == "req-001"
        assert len(resp.prioritized_tasks) == 1
        assert resp.prioritized_tasks[0].rank == 1

    def test_response_with_empty_tasks(self):
        """Test response with empty task list."""
        resp = TaskPrioritizationResponse(
            prioritized_tasks=[],
            summary="No tasks"
        )
        assert resp.prioritized_tasks == []
