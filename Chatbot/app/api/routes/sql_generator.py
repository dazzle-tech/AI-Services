"""SQL generator API routes."""
import logging
from fastapi import APIRouter, HTTPException
from app.models.schemas import SQLGeneratorRequest, SQLGeneratorResponse
from app.services.sql_generation import SQLGenerationService

logger = logging.getLogger(__name__)

router = APIRouter()

# Initialize service
_sql_service = SQLGenerationService()


@router.post("/generate", response_model=SQLGeneratorResponse)
@router.post("/generate_sql", response_model=SQLGeneratorResponse)
def generate_sql(req: SQLGeneratorRequest) -> SQLGeneratorResponse:
    """Generate SQL from natural language."""
    logger.info(f"🧠 Incoming SQL generation request for {req.user_id}")
    
    try:
        sql_query = _sql_service.generate_sql(req.user_id, req.text)
        logger.info(f"✅ Final SQL: {sql_query}")
        return SQLGeneratorResponse(
            user_id=req.user_id,
            input_text=req.text,
            sql_query=sql_query
        )
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("SQL generation error")
        raise HTTPException(status_code=500, detail=f"Model generation error: {e}")



