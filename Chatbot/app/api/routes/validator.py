"""Validator API routes."""
import logging
from fastapi import APIRouter, HTTPException
from app.models.schemas import ValidatorRequest, ValidatorResponse
from app.services.validation import ValidationService

logger = logging.getLogger(__name__)

router = APIRouter()

# Initialize service
_validation_service = ValidationService()


@router.post("/validate", response_model=ValidatorResponse)
@router.post("/validate_and_execute", response_model=ValidatorResponse)
def validate(req: ValidatorRequest) -> ValidatorResponse:
    """Validate and execute SQL query."""
    logger.info(f"📨 Received validation request for user: {req.user_id}")
    
    try:
        result = _validation_service.validate_and_execute(req.user_id, req.sql_query)
        logger.info(f"📤 Returning validation result for {req.user_id}: {result.get('message', '')}")
        return ValidatorResponse(
            user_id=req.user_id,
            sql_query=req.sql_query,
            validation_result=result
        )
    except FileNotFoundError as e:
        logger.error(f"❌ {e}")
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        logger.error(f"❌ {e}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Validation error")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/")
def root():
    """Root endpoint."""
    return {"ok": True, "service": "Validator+Executor", "docs": "/docs"}



