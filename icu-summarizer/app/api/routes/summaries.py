"""Summaries endpoint"""
from fastapi import APIRouter, Request, Depends, status
from fastapi.responses import JSONResponse

from app.domain.input_models import ICURequestPayload
from app.application.summarize_use_case import SummarizeUseCase
from app.utils.errors import ValidationError, ExternalServiceError

router = APIRouter()

# Global variable to hold the use case (set by main.py)
_summarize_use_case_instance = None


def get_summarize_use_case() -> SummarizeUseCase:
    """Dependency - will be set by main.py"""
    if _summarize_use_case_instance is None:
        raise RuntimeError("OpenAI API key not configured. Set OPENAI_API_KEY environment variable.")
    return _summarize_use_case_instance


@router.post("/v1/summaries")
async def create_summary(
    payload: ICURequestPayload,
    request: Request,
    summarize_use_case: SummarizeUseCase = Depends(get_summarize_use_case)
):
    """
    Generate ICU daily summary.
    
    Returns markdown note, structured JSON, warnings, and source counts.
    """
    try:
        result = summarize_use_case.execute(payload)
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=result
        )
    
    except ValidationError as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": {
                    "code": e.code,
                    "message": e.message,
                    "request_id": getattr(request.state, "request_id", None)
                }
            }
        )
    
    except ExternalServiceError as e:
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={
                "error": {
                    "code": e.code,
                    "message": e.message,
                    "request_id": getattr(request.state, "request_id", None)
                }
            }
        )
    
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": str(e),
                    "request_id": getattr(request.state, "request_id", None)
                }
            }
        )
