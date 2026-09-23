"""Patient agent HTTP API.

Endpoints mirror the clinician agent's paths and payloads (`/agent/chat`,
`/agent/chat/stream`) so one shared frontend chat component can drive either.
"""
import json
import logging
from typing import Dict, Iterator, List, Optional, Tuple

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.agents import llm, nodes
from app.agents.graph import run_turn
from app.infrastructure import tools
from app.infrastructure.session_store import get_session_store
from app.models import schemas

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent")

_HISTORY_LIMIT = 20

SUGGESTIONS = [
    "When is my next appointment?",
    "What medication am I taking?",
    "What are your visiting hours?",
    "Book me an appointment",
]


def _greeting_text(name: Optional[str]) -> str:
    who = f", {name.split()[0]}" if name else ""
    return (
        f"Hello{who} — I'm the Riverside General Hospital assistant.\n\n"
        "I can help you with your appointments, look up what's in your own health "
        "record, and answer general questions about the hospital.\n\n"
        "I can't give medical advice or explain what a result means — your care team "
        "is the right person for that. If something feels urgent, please call 911.\n\n"
        "What can I help you with?"
    )


def _bind_identity(session: Dict, req: schemas.PatientChatRequest) -> Tuple[int, Optional[str], Optional[str]]:
    """Resolve the patient identity for this turn, and pin it to the session."""
    bound = session.get("patient_id")
    if bound is None:
        if req.patient_id is None:
            raise HTTPException(
                status_code=401,
                detail="Please sign in — I need to know who you are before I can help.",
            )
        return int(req.patient_id), req.patient_mrn, req.patient_name
    if req.patient_id is not None and int(req.patient_id) != int(bound):
        logger.warning("session %s is bound to patient %s but request presented %s",
                       req.session_id, bound, req.patient_id)
        raise HTTPException(
            status_code=409,
            detail="This conversation belongs to a different account. Please sign out "
                   "and sign in again to start a new conversation.",
        )
    return int(bound), session.get("patient_mrn") or req.patient_mrn, session.get("patient_name") or req.patient_name


def _persist(session_id: str, session: Dict, message: str, final: Dict,
             patient_id: int, patient_mrn: Optional[str], patient_name: Optional[str]) -> None:
    history: List[Dict[str, str]] = session.get("history") or []
    updated = history + [
        {"role": "user", "content": message},
        {"role": "assistant", "content": final.get("text", "")},
    ]
    patch: Dict = {
        "history": updated[-_HISTORY_LIMIT:],
        "patient_id": patient_id,
        "patient_mrn": patient_mrn,
        "patient_name": patient_name,
    }
    # A turn either stages a new confirmation, clears one, or leaves it alone.
    if final.get("_pending"):
        patch["pending"] = final["_pending"]
    elif final.get("_pending_cleared"):
        patch["pending"] = None
    # Carry forward the slots the scheduler last offered (booking resolves against them).
    if final.get("_slots") is not None:
        patch["last_slots"] = final["_slots"]
    if final.get("_appts") is not None:
        patch["last_appointments"] = final["_appts"]
    try:
        get_session_store().update(session_id, patch)
    except Exception as exc:
        logger.warning("failed to persist session %s: %s", session_id, exc)


@router.get("/greeting", response_model=schemas.GreetingResponse)
def greeting(patient_name: Optional[str] = None) -> schemas.GreetingResponse:
    """Opening message shown when the chat is first opened.

    Deterministic — no model call — so the first thing a patient sees is always the
    same, always on-policy, and instant.
    """
    return schemas.GreetingResponse(text=_greeting_text(patient_name), suggestions=SUGGESTIONS)


@router.get("/history", response_model=schemas.HistoryResponse)
def history(session_id: str = "default") -> schemas.HistoryResponse:
    session = get_session_store().get(session_id)
    return schemas.HistoryResponse(session_id=session_id, history=session.get("history") or [])


@router.post("/reset")
def reset(session_id: str = "default") -> Dict:
    """Clear a conversation (used on sign-out)."""
    get_session_store().clear(session_id)
    return {"ok": True, "session_id": session_id}


@router.post("/chat", response_model=schemas.PatientChatResponse)
def chat(req: schemas.PatientChatRequest) -> schemas.PatientChatResponse:
    store = get_session_store()
    session = store.get(req.session_id)
    patient_id, patient_mrn, patient_name = _bind_identity(session, req)

    final = run_turn(
        req.message,
        patient_id=patient_id,
        patient_mrn=patient_mrn,
        patient_name=patient_name,
        conversation=session.get("history") or [],
        session_id=req.session_id,
        pending=session.get("pending"),
        last_slots=session.get("last_slots"),
        last_appointments=session.get("last_appointments"),
    )
    _persist(req.session_id, session, req.message, final, patient_id, patient_mrn, patient_name)

    return schemas.PatientChatResponse(
        text=final.get("text", ""),
        html=final.get("html"),
        data_json=final.get("data_json"),
        action=final.get("action"),
        service=final.get("service"),
    )


def _stream_events(req: schemas.PatientChatRequest, session: Dict,
                   patient_id: int, patient_mrn: Optional[str],
                   patient_name: Optional[str]) -> Iterator[Tuple[str, Dict]]:
    """One turn as (event, data) tuples: status / token / done.

    Runs the same nodes as the graph, but streams the presentation step — the only step
    slow enough for streaming to be worth it. Short replies (chat/clarify/refuse and
    confirmations) are emitted whole, rather than faked into tokens.
    """
    state: Dict = {
        "user_message": req.message,
        "conversation": session.get("history") or [],
        "session_id": req.session_id,
        "language": "ar" if nodes._has_arabic(req.message) else "en",
        "patient_id": patient_id,
        "patient_mrn": patient_mrn,
        "patient_name": patient_name,
        "pending": session.get("pending"),
        "last_slots": session.get("last_slots") or [],
        "last_appointments": session.get("last_appointments") or [],
    }

    yield ("status", {"stage": "thinking"})

    state = nodes.gate_node(state)
    if not state.get("final"):
        state = nodes.router_node(state)

    if not state.get("final"):
        operation = state.get("operation")
        yield ("status", {"stage": "tool", "service": operation})
        state = nodes.collect_node(state)

        if not state.get("final"):
            yield ("status", {"stage": "executing", "service": operation})
            op = tools.OPERATIONS.get(operation)
            try:
                state["result"] = tools.call(
                    operation, state.get("params") or {},
                    patient_id=patient_id, patient_mrn=patient_mrn)
                if operation == "appointments_search":
                    state["slots_out"] = (state["result"].get("slots") or [])[:10]
                elif operation == "appointments_list":
                    state["appts_out"] = state["result"].get("upcoming") or []
            except tools.ToolError as exc:
                state["final"] = {"text": str(exc), "html": None, "data_json": None,
                                  "action": "error",
                                  "service": op.service if op else None}
            except Exception:
                logger.exception("stream tool failure for %s", operation)
                state["final"] = {"text": "Sorry — something went wrong on our side. "
                                          "Please try again in a moment.",
                                  "html": None, "data_json": None, "action": "error",
                                  "service": op.service if op else None}

            if not state.get("final"):
                yield ("status", {"stage": "answering"})
                text = ""
                for token in llm.stream(nodes.present_prompt(state), temperature=0.3,
                                        max_tokens=600, model=llm.ANSWER_MODEL):
                    text += token
                    yield ("token", {"t": token})
                if not text.strip():
                    text = nodes._fallback_text(operation, state.get("result") or {})
                    yield ("token", {"t": text})
                state["final"] = {
                    "text": text, "html": None, "data_json": state.get("result"),
                    "action": "use_tool", "service": op.service if op else None,
                }

    final = state.get("final") or {
        "text": "How can I help?", "html": None, "data_json": None,
        "action": "chat", "service": None,
    }
    # Short replies were never streamed above — emit them now so the UI has text.
    if final.get("action") != "use_tool" and final.get("text"):
        yield ("token", {"t": final["text"]})

    final["_pending"] = state.get("pending_out")
    final["_pending_cleared"] = bool(state.get("pending_cleared"))
    final["_slots"] = state.get("slots_out")
    final["_appts"] = state.get("appts_out")
    _persist(req.session_id, session, req.message, final, patient_id, patient_mrn, patient_name)

    yield ("done", {k: v for k, v in final.items() if not k.startswith("_")})


@router.post("/chat/stream")
def chat_stream(req: schemas.PatientChatRequest):
    """SSE variant of /chat — `status` events, streamed tokens, then the final payload."""
    store = get_session_store()
    session = store.get(req.session_id)
    patient_id, patient_mrn, patient_name = _bind_identity(session, req)

    def gen():
        try:
            for event, data in _stream_events(req, session, patient_id, patient_mrn, patient_name):
                yield f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        except Exception:
            logger.exception("patient stream failed")
            payload = {"text": "Sorry — I hit a problem just then. Please try again.",
                       "html": None, "data_json": None, "action": "error", "service": None}
            yield f"event: done\ndata: {json.dumps(payload)}\n\n"

    return StreamingResponse(
        gen(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                 "Connection": "keep-alive"},
    )


@router.get("/tools")
def tool_status() -> Dict:
    """Which patient tools are configured and reachable."""
    ops = tools.active_operations()
    return {
        "services": tools.health(),
        "operations": sorted(ops),
    }
