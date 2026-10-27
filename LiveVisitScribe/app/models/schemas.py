"""Message shapes for WS /api/v1/live."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Speaker = Literal["doctor", "patient"]
Lang = Literal["en", "ar"]


class PatientContext(BaseModel):
    """Chart background sent with `start`. Used only so it is not repeated as a new finding."""

    model_config = ConfigDict(extra="ignore")

    chronic_diseases: list[str] = Field(default_factory=list)
    active_medications: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    known_diagnoses: list[str] = Field(default_factory=list)


class StartMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["start"]
    sample_rate: int = Field(default=16000, ge=8000, le=48000)
    channels: int = Field(default=1, ge=1, le=2)
    patient_context: Optional[PatientContext] = None


class Segment(BaseModel):
    id: str
    speaker: Speaker
    start_ms: int
    end_ms: int
    text: str
    lang: Lang
    final: bool
    low_confidence_numbers: list[str] = Field(default_factory=list)


class Evidence(BaseModel):
    text: str
    segment_ids: list[str]


class Medication(BaseModel):
    name: str
    detail: Optional[str] = None
    confirm: Literal[True] = True
    segment_ids: list[str]


class PickedUp(BaseModel):
    complaint: Optional[Evidence] = None
    symptoms: list[Evidence] = Field(default_factory=list)
    medications: list[Medication] = Field(default_factory=list)
    exam: list[Evidence] = Field(default_factory=list)
    # Asklepios payloads so far (same shapes as ConvoVoiceAgent /draft `record`). record[group] is null until
    # something is found for it; record_evidence maps "group.field" to segment ids; missing_required lists
    # required fields not said yet. Diagnoses come from ConvoVoiceAgent when the visit is stopped.
    record: dict[str, Any] = Field(default_factory=dict)
    record_evidence: dict[str, list[str]] = Field(default_factory=dict)
    record_status: dict[str, str] = Field(default_factory=dict)
    missing_required: dict[str, list[str]] = Field(default_factory=dict)

    def is_empty(self) -> bool:
        has_record = any(value for value in self.record.values())
        return self.complaint is None and not (self.symptoms or self.medications or self.exam or has_record)
