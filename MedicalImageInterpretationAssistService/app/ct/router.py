from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from slowapi import Limiter
from slowapi.util import get_remote_address

from .. import config
from ..config import Settings
from ..storage import temp_workdir
from ..interpretation.models import AIInfo, InterpretationResponse, StudyInfo
from ..interpretation.interpretation_service import localize_response
from .ct_service import build_ct_response

ct_router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


def _get_settings() -> Settings:
    return config.get_settings()


@ct_router.get("/health")
def ct_health() -> dict:
    return {"status": "ok", "service": "ct-interpretation-assist"}


@ct_router.post("/dicom", response_model=InterpretationResponse)
@limiter.limit("10/minute")
async def ct_dicom(
    request: Request,
    file: UploadFile = File(...),
    clinical_indication: str | None = Form(None),
    OutputLanguage: str = Form("el"),
    settings: Settings = Depends(_get_settings),
) -> InterpretationResponse:
    max_bytes = settings.max_upload_mb * 1024 * 1024
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Upload exceeds maximum allowed size of {settings.max_upload_mb} MB.",
        )

    chunk_size = 1024 * 1024
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
            return build_ct_response(
                upload_input_path=upload_path,
                workdir=workdir,
                clinical_indication=clinical_indication,
                output_language=OutputLanguage,
                settings=settings,
                max_slices=settings.ct_max_slices,
            )
        except Exception as e:
            return localize_response(InterpretationResponse(
                exam_type="CT_UNKNOWN",
                status="REVIEW_REQUIRED",
                findings=[],
                critical_alert=False,
                summary="CT pipeline error. Radiologist review required.",
                study=StudyInfo(modality="CT", body_part=None, view="AXIAL"),
                ai=AIInfo(model_name="unknown", modality_handled="CT", slices_reviewed=0, not_for_medical_use=True),
                warnings=[str(e)],
                disclaimer=settings.disclaimer_text,
            ), OutputLanguage)
