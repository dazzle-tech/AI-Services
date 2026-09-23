"""Shared state for the patient agent's LangGraph workflow."""
from typing import Any, Dict, List, Optional, TypedDict


class PatientAgentState(TypedDict, total=False):
    # ---- inputs ----
    user_message: str
    conversation: List[Dict[str, str]]
    session_id: str
    language: str                       # "en" | "ar"

    # ---- identity (authoritative; comes from the session, never the message) ----
    patient_id: Optional[int]
    patient_mrn: Optional[str]
    patient_name: Optional[str]

    # ---- pending write awaiting confirmation, carried in the session ----
    pending: Optional[Dict[str, Any]]   # {operation, params, description}

    # ---- slots from the last appointments_search, carried in the session ----
    # Booking resolves the chosen slot from THIS list rather than from model output, so
    # provider_id/date/time always come from something the scheduler actually offered.
    last_slots: List[Dict[str, Any]]
    # Same idea for cancellation: the appointments last shown to the patient, so an
    # appt_id always comes from a real row of theirs rather than a model-invented index.
    last_appointments: List[Dict[str, Any]]

    # ---- router ----
    decision: Dict[str, Any]            # {action, operation, params, reply, reason}
    operation: Optional[str]

    # ---- collect ----
    params: Dict[str, Any]
    missing: List[str]

    # ---- execute ----
    result: Optional[Dict[str, Any]]
    tool_error: Optional[str]

    # ---- output ----
    final: Dict[str, Any]               # {text, html, data_json, action, service}
    # Set when this turn produced/cleared a pending confirmation, so the route handler
    # can persist it onto the session.
    pending_out: Optional[Dict[str, Any]]
    pending_cleared: bool
    slots_out: Optional[List[Dict[str, Any]]]
    appts_out: Optional[List[Dict[str, Any]]]
