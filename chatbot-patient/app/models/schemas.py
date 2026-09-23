"""API schemas for the patient agent.

The response shape is deliberately identical to the clinician agent's
(`text` / `html` / `data_json` / `action` / `service`) so the shared React
`<ChatPanel>` added in Phase 4 works against either bot unchanged.
"""
from typing import List, Optional

from pydantic import BaseModel, Field


class PatientChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    # Identity of the signed-in patient. Bound to the session on the first turn; a
    # later turn that disagrees is rejected rather than silently switching patients.
    patient_id: Optional[int] = None
    patient_mrn: Optional[str] = None
    patient_name: Optional[str] = None
    # Accepted for wire-compatibility with the clinician client. `role` is ignored —
    # this service is patient-only — and the model tier is not caller-selectable.
    user_id: str = "patient"
    role: str = "patient"
    language: str = "en"
    reasoning_model: Optional[str] = None


class PatientChatResponse(BaseModel):
    text: str
    html: Optional[str] = None
    data_json: Optional[dict] = None
    action: Optional[str] = None
    service: Optional[str] = None


class GreetingResponse(BaseModel):
    text: str
    suggestions: List[str] = Field(
        default_factory=list, description="Quick-action prompts for the UI"
    )


class HistoryResponse(BaseModel):
    session_id: str
    history: List[dict] = []
