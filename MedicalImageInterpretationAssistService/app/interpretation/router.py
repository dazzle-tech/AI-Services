from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from slowapi import Limiter
from slowapi.util import get_remote_address

from ..config import Settings, get_settings
from ..storage import temp_workdir
from .interpretation_service import build_dicom_response
from .models import AIInfo, InterpretationResponse, StudyInfo
from .xray_model import model_status

interpretation_router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@interpretation_router.get("/health")
def interpretation_health(settings: Settings = Depends(get_settings)) -> dict:
    status = model_status(settings.openai_api_key)
    return {"status": "ok", "service": "xray-interpretation-assist", **status}


@interpretation_router.post("/dicom", response_model=InterpretationResponse)
@limiter.limit("20/minute")
async def interpretation_dicom(
    request: Request,
    file: UploadFile = File(...),
    clinical_indication: str | None = Form(None),
    settings: Settings = Depends(get_settings),
) -> InterpretationResponse:
    max_bytes = settings.max_upload_mb * 1024 * 1024
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Upload exceeds maximum allowed size of {settings.max_upload_mb} MB.",
        )

    chunk_size = 1024 * 1024  # 1 MB
    chunks = []
    total = 0
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"Upload exceeds maximum allowed size of {settings.max_upload_mb} MB.",
            )
        chunks.append(chunk)
    file_bytes = b"".join(chunks)

    with temp_workdir() as workdir:
        upload_path = workdir / (file.filename or "upload.dcm")
        upload_path.write_bytes(file_bytes)
        try:
            return build_dicom_response(
                upload_input_path=upload_path,
                workdir=workdir,
                clinical_indication=clinical_indication,
                settings=settings,
            )
        except Exception as e:
            return InterpretationResponse(
                exam_type="XR_UNKNOWN",
                status="REVIEW_REQUIRED",
                findings=[],
                critical_alert=False,
                summary="No AI candidate acute finding identified above configured thresholds. Radiologist review required.",
                study=StudyInfo(),
                ai=AIInfo(model_name="unknown", modality_handled="XRAY", slices_reviewed=1, not_for_medical_use=True),
                warnings=[f"Pipeline error: {e}"],
                disclaimer=settings.disclaimer_text,
            )
