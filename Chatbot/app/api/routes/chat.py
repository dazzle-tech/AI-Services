"""Chat API routes."""
import os
import time
import logging
import sys
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from app.models.schemas import ChatRequest, ChatResponse
from app.services.chat_orchestrator import ChatOrchestratorService
from app.services.session_memory import SessionMemoryService
from app.services.identity import get_identity_resolver
from app.services.rate_limiter import get_rate_limiter

logger = logging.getLogger(__name__)
# Ensure logger propagates to root logger (which has file handler)
logger.setLevel(logging.INFO)
logger.propagate = True  # Allow logs to propagate to root logger
# Don't add separate handlers - use root logger's handlers

router = APIRouter()

# Initialize services
_orchestrator = ChatOrchestratorService()
_session_memory = SessionMemoryService()
_identity_resolver = get_identity_resolver()
_rate_limiter = get_rate_limiter()


@router.post("/chat", response_model=ChatResponse)
def chat(request: Request, req: ChatRequest) -> ChatResponse:
    """Main chat endpoint."""
    raw_message = (req.message or "").strip()
    if not raw_message:
        raise HTTPException(status_code=400, detail="Empty message.")

    resolved = _identity_resolver.resolve_from_web(request, user_id_hint=req.user_id)
    _rate_limiter.check(resolved.user_id, channel=resolved.channel)
    session_id = req.session_id or f"session_{int(time.time())}"
    user_id = resolved.user_id
    role = resolved.role
    
    # Force log to ensure visibility - write directly to file as backup
    try:
        # Calculate path: chat.py is in chatbot/app/api/routes/, need to go up 3 levels to chatbot/
        log_file = Path(__file__).parent.parent.parent / "orchestrator.log"
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"\n[{time.time()}] [ROUTE] /chat called: message='{raw_message}', user_id={user_id}, channel={resolved.channel}\n")
            f.flush()
            os.fsync(f.fileno())  # Force write to disk
    except Exception as e:
        print(f"[ERROR] Failed to write to log file: {e}", flush=True, file=sys.stderr)
    
    # Also use logger
    logger.info(f"🔵 [ROUTE] /chat called: message='{raw_message}', user_id={user_id}, session_id={session_id}")
    root_logger = logging.getLogger()
    root_logger.info(f"🔵 ROUTE: /chat - message='{raw_message}'")
    print(f"[CHAT ROUTE] Processing: '{raw_message}' for user {user_id}", flush=True, file=sys.stderr)
    print(f"[CHAT ROUTE] Processing: '{raw_message}' for user {user_id}", flush=True, file=sys.stdout)
    sys.stdout.flush()
    sys.stderr.flush()
    
    try:
        result = _orchestrator.process_chat(
            raw_message=raw_message,
            user_id=user_id,
            session_id=session_id,
            role=role,
            approved=req.approved,
            correction_rejected=req.correction_rejected,
        )
        logger.info(f"✅ [ROUTE] /chat completed: intent={result.get('intent')}, text_length={len(result.get('text', ''))}")
        print(f"[CHAT ROUTE] Completed: intent={result.get('intent')}")
        return ChatResponse(**result)
    except Exception as e:
        logger.error(f"❌ [ROUTE] Error processing chat: {e}", exc_info=True)
        print(f"[CHAT ROUTE] ERROR: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat_crewai", response_model=ChatResponse)
def chat_crewai(request: Request, req: ChatRequest) -> ChatResponse:
    """CrewAI-powered chat endpoint."""
    from app.crewai.crew import build_medai_crew
    from app.infrastructure.db.audit_repo import AuditRepository
    
    raw_message = (req.message or "").strip()
    if not raw_message:
        raise HTTPException(status_code=400, detail="Empty message.")

    resolved = _identity_resolver.resolve_from_web(request, user_id_hint=req.user_id)
    _rate_limiter.check(resolved.user_id, channel=resolved.channel)
    session_id = req.session_id or f"session_{int(time.time())}"
    user_id = resolved.user_id
    role = resolved.role
    
    audit_repo = AuditRepository()
    interaction_id = audit_repo.insert_interaction(
        user_id=user_id,
        session_id=session_id,
        role=role,
        intent="chat_crewai",
        approved=True,
        raw_message=raw_message,
        final_message=raw_message,
    )
    
    try:
        crew = build_medai_crew(raw_message, user_id, role)
        result = crew.kickoff(inputs={"message": raw_message, "user_id": user_id, "role": role})
        reply = str(result)
        audit_repo.update_interaction(interaction_id, reply_text=reply, row_count=0)
        return ChatResponse(intent="crewai", text=reply)
    except Exception as e:
        logger.error(f"CrewAI error: {e}", exc_info=True)
        audit_repo.update_interaction(interaction_id, ok=False, error=str(e))
        raise HTTPException(status_code=500, detail=f"CrewAI failed: {e}")


@router.get("/session_memory")
def get_sessions():
    """Get all sessions (debug endpoint)."""
    return {"active_sessions": len(_session_memory.get_all_sessions()), "sessions": _session_memory.get_all_sessions()}


@router.post("/reset_sessions")
def reset_sessions():
    """Reset all sessions."""
    _session_memory.clear_all_sessions()
    return {"ok": True}


@router.get("/test_logging")
def test_logging():
    """Test endpoint to verify logging works."""
    print("=" * 50, flush=True)
    print("[TEST] Logging test endpoint called!", flush=True)
    logger.info("🔵 [TEST] Logging test - INFO level")
    logger.warning("⚠️ [TEST] Logging test - WARNING level")
    logger.error("❌ [TEST] Logging test - ERROR level")
    print("[TEST] This is a print statement", flush=True)
    sys.stdout.flush()
    sys.stderr.flush()
    print("=" * 50, flush=True)
    return {"ok": True, "message": "Check terminal for logs"}
