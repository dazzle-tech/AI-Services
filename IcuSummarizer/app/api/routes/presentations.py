"""Presentations endpoint"""
import json
from fastapi import APIRouter, Request, Depends, status
from fastapi.responses import Response

from app.domain.input_models import ICURequestPayload
from app.application.presentation_use_case import PresentationUseCase
from app.utils.errors import ValidationError, ExternalServiceError

router = APIRouter()

# Global variable to hold the use case (set by main.py)
_presentation_use_case_instance = None


def get_presentation_use_case() -> PresentationUseCase:
    """Dependency - will be set by main.py"""
    if _presentation_use_case_instance is None:
        raise RuntimeError("OpenAI API key not configured. Set OPENAI_API_KEY environment variable.")
    return _presentation_use_case_instance


@router.post("/v1/presentations")
async def create_presentation(
    payload: ICURequestPayload,
    request: Request,
    presentation_use_case: PresentationUseCase = Depends(get_presentation_use_case)
):
    """
    Generate ICU handoff presentation (PPTX).
    
    Returns PPTX file as download.
    """
    try:
        pptx_bytes = presentation_use_case.execute(payload)
        
        # Generate filename
        patient_id = payload.patient.id
        start_str = payload.time_window.start.strftime("%Y%m%d_%H%M%S")
        end_str = payload.time_window.end.strftime("%Y%m%d_%H%M%S")
        filename = f"icu_handoff_{patient_id}_{start_str}_{end_str}.pptx"
        
        return Response(
            content=pptx_bytes.read(),
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "X-Request-ID": getattr(request.state, "request_id", None) or ""
            }
        )
    
    except ValidationError as e:
        error_response = {
            "error": {
                "code": e.code,
                "message": e.message,
                "request_id": getattr(request.state, "request_id", None)
            }
        }
        return Response(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=json.dumps(error_response),
            media_type="application/json"
        )
    
    except ExternalServiceError as e:
        error_response = {
            "error": {
                "code": e.code,
                "message": e.message,
                "request_id": getattr(request.state, "request_id", None)
            }
        }
        return Response(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content=json.dumps(error_response),
            media_type="application/json"
        )
    
    except Exception as e:
        error_response = {
            "error": {
                "code": "INTERNAL_ERROR",
                "message": str(e),
                "request_id": getattr(request.state, "request_id", None)
            }
        }
        return Response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=json.dumps(error_response),
            media_type="application/json"
        )
