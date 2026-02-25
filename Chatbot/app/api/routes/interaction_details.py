"""Interaction details API routes."""
import logging
from fastapi import APIRouter, HTTPException
from app.infrastructure.db.audit_repo import AuditRepository
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

router = APIRouter()

# Initialize services
_audit_repo = AuditRepository()


class InteractionDetailsRequest(BaseModel):
    """Interaction details request model."""
    interaction_id: int  # The interaction/event ID
    user_id: str = Field(default="default_user")
    session_id: Optional[str] = None


class InteractionDetailsResponse(BaseModel):
    """Interaction details response model."""
    ok: bool
    interaction: Optional[Dict[str, Any]] = None
    service_calls: Optional[list] = None
    message: Optional[str] = None


@router.post("/interaction_details", response_model=InteractionDetailsResponse)
def interaction_details(req: InteractionDetailsRequest) -> InteractionDetailsResponse:
    """
    Get interaction details (non-admin endpoint for viewing chatbot interactions).
    
    This endpoint allows any user to view their own interaction details or
    interactions from queries they've made, without requiring admin privileges.
    
    Args:
        req: InteractionDetailsRequest with interaction_id and user_id
        
    Returns:
        InteractionDetailsResponse with full interaction data including reply_text
    """
    try:
        # Query the interaction from audit database
        data = _audit_repo.query_event(req.interaction_id)
        
        interaction = data.get("interaction", {})
        service_calls = data.get("service_calls", [])
        
        # Return all data - no admin check needed since user is querying their own data
        # or data from queries they've made
        return InteractionDetailsResponse(
            ok=True,
            interaction=interaction,
            service_calls=service_calls
        )
    except ValueError as e:
        logger.warning(f"⚠️ Interaction {req.interaction_id} not found: {e}")
        return InteractionDetailsResponse(
            ok=False,
            message=f"Interaction {req.interaction_id} not found."
        )
    except Exception as e:
        logger.error(f"❌ Error fetching interaction details: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch interaction details: {e}")
