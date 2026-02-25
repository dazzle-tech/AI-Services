"""Admin audit API routes."""
import logging
import re
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from app.models.schemas import AdminHistoryResponse, AdminEventResponse, AdminSearchResponse
from app.infrastructure.db.audit_repo import AuditRepository
from app.infrastructure.config.access_control_repo import AccessControlRepository

logger = logging.getLogger(__name__)

router = APIRouter()

# Initialize services
_audit_repo = AuditRepository()
_access_control = AccessControlRepository()


def _require_admin(admin_user_id: str):
    """Check if user is admin."""
    role = _access_control.get_user_role(admin_user_id)
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required.")


@router.get("/admin/history")
def admin_history(
    admin_user_id: str = Query(...),
    user_id: Optional[str] = Query(None),
    range: Optional[str] = Query(None, description="today | yesterday | <Nd> (e.g. 7d)"),
    session_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
) -> AdminHistoryResponse:
    """Get admin history."""
    _require_admin(admin_user_id)
    start_utc, end_utc = _audit_repo.parse_range(range or "")
    rows = _audit_repo.query_history(user_id=user_id, session_id=session_id, start_utc=start_utc, end_utc=end_utc, limit=limit)
    return AdminHistoryResponse(ok=True, count=len(rows), rows=rows)


@router.get("/admin/history/event/{event_id}")
def admin_history_event(event_id: int, admin_user_id: str = Query(...)) -> AdminEventResponse:
    """Get event details."""
    _require_admin(admin_user_id)
    try:
        data = _audit_repo.query_event(event_id)
        return AdminEventResponse(ok=True, data=data)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/admin/history/session/{session_id}")
def admin_history_session(
    session_id: str,
    admin_user_id: str = Query(...),
    limit: int = Query(200, ge=1, le=2000),
) -> AdminHistoryResponse:
    """Get session history."""
    _require_admin(admin_user_id)
    rows = _audit_repo.query_history(user_id=None, session_id=session_id, start_utc=None, end_utc=None, limit=limit)
    return AdminHistoryResponse(ok=True, count=len(rows), rows=rows)


@router.get("/admin/search")
def admin_search(
    admin_user_id: str = Query(...),
    q: str = Query(...),
    limit: int = Query(25, ge=1, le=200),
) -> AdminSearchResponse:
    """Search interactions."""
    _require_admin(admin_user_id)
    rows = _audit_repo.search(q, limit=limit)
    return AdminSearchResponse(ok=True, count=len(rows), rows=rows)



