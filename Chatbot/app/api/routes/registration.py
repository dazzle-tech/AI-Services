"""Registration API routes — admin phone mapping and patient OTP self-registration."""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.infrastructure.config.access_control_repo import AccessControlRepository
from app.infrastructure.db.hospital_repo import HospitalRepository
from app.infrastructure.db.registered_users_repo import RegisteredUsersRepository
from app.services.identity import IdentityResolver
from app.services.otp_service import OTPService

logger = logging.getLogger(__name__)

router = APIRouter()

_access_control = AccessControlRepository()
_registered_users = RegisteredUsersRepository()
_hospital_repo = HospitalRepository()
_otp_service = OTPService()
_identity = IdentityResolver(
    access_control=_access_control,
    registered_users_repo=_registered_users,
)


def _require_admin(admin_user_id: str) -> None:
    role = _access_control.get_user_role(admin_user_id)
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required.")


class RegisterPhoneRequest(BaseModel):
    phone_number: str
    user_id: str
    role: str
    otp_verified: bool = True


class PatientRegisterStartRequest(BaseModel):
    medical_record_number: str
    phone_number: str


class PatientRegisterVerifyRequest(BaseModel):
    medical_record_number: str
    phone_number: str
    otp_code: str


@router.post("/admin/register_phone")
def admin_register_phone(
    req: RegisterPhoneRequest,
    admin_user_id: str = Query(...),
) -> dict:
    """Admin-only: add or update a phone → user mapping."""
    _require_admin(admin_user_id)
    try:
        normalized = IdentityResolver.normalize_phone(req.phone_number)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not _access_control.get_user_access(req.user_id):
        raise HTTPException(status_code=400, detail=f"Unknown user_id: {req.user_id}")

    allowed_roles = {"doctor", "nurse", "admin", "patient"}
    if req.role not in allowed_roles:
        raise HTTPException(status_code=400, detail=f"Invalid role: {req.role}")

    _registered_users.upsert(
        normalized,
        req.user_id,
        req.role,
        registered_by=admin_user_id,
        active=True,
        otp_verified=req.otp_verified,
    )
    logger.info("Admin %s registered phone %s → %s (%s)", admin_user_id, normalized, req.user_id, req.role)
    return {"ok": True, "phone_number": normalized, "user_id": req.user_id, "role": req.role}


@router.post("/admin/deactivate_phone")
def admin_deactivate_phone(
    phone_number: str = Query(...),
    admin_user_id: str = Query(...),
) -> dict:
    """Admin-only: deactivate a phone mapping."""
    _require_admin(admin_user_id)
    try:
        normalized = IdentityResolver.normalize_phone(phone_number)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not _registered_users.set_active(normalized, False):
        raise HTTPException(status_code=404, detail="Phone number not registered.")
    return {"ok": True, "phone_number": normalized, "active": False}


@router.get("/admin/registered_phones")
def admin_list_registered_phones(
    admin_user_id: str = Query(...),
    active_only: bool = Query(False),
) -> dict:
    """Admin-only: list registered phone mappings."""
    _require_admin(admin_user_id)
    rows = _registered_users.list_all(active_only=active_only)
    return {"ok": True, "count": len(rows), "rows": rows}


@router.post("/register/patient/start")
def patient_register_start(req: PatientRegisterStartRequest) -> dict:
    """
    Patient self-registration: verify MRN exists and phone matches hospital record,
    then send OTP. Role is always 'patient' — never self-assigned.
    """
    mrn = str(req.medical_record_number).strip()
    try:
        normalized = IdentityResolver.normalize_phone(req.phone_number)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    on_file = _hospital_repo.fetch_phone_by_mrn(mrn)
    if not on_file:
        raise HTTPException(
            status_code=404,
            detail="No phone number on file for this medical record number.",
        )

    if not _phones_match(on_file, normalized):
        raise HTTPException(
            status_code=403,
            detail="Phone number does not match the number on file for this MRN.",
        )

    patient_user_id = f"patient_{mrn}"
    otp = _otp_service.generate(normalized, purpose="patient_registration")

    # In production, send OTP via SMS provider — log only in dev
    logger.info(
        "Patient registration OTP for MRN %s / %s (dev log only — integrate SMS in production)",
        mrn,
        normalized,
    )

    return {
        "ok": True,
        "message": "OTP sent to the phone number on file.",
        "phone_number": normalized,
        # Dev-only hint — remove in production SMS integration
        "dev_otp_hint": otp if logger.isEnabledFor(logging.DEBUG) else None,
    }


@router.post("/register/patient/verify")
def patient_register_verify(req: PatientRegisterVerifyRequest) -> dict:
    """Complete patient self-registration after OTP verification."""
    mrn = str(req.medical_record_number).strip()
    try:
        normalized = IdentityResolver.normalize_phone(req.phone_number)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    on_file = _hospital_repo.fetch_phone_by_mrn(mrn)
    if not on_file or not _phones_match(on_file, normalized):
        raise HTTPException(status_code=403, detail="Phone/MRN verification failed.")

    if not _otp_service.verify(normalized, req.otp_code, purpose="patient_registration"):
        raise HTTPException(status_code=403, detail="Invalid or expired OTP.")

    patient_user_id = f"patient_{mrn}"
    _registered_users.upsert(
        normalized,
        patient_user_id,
        "patient",
        registered_by="self_registration",
        active=True,
        otp_verified=True,
    )
    return {
        "ok": True,
        "phone_number": normalized,
        "user_id": patient_user_id,
        "role": "patient",
    }


def _phones_match(on_file: str, submitted: str) -> bool:
    """Compare phone numbers ignoring formatting."""
    import re

    def digits(p: str) -> str:
        return re.sub(r"\D", "", p or "")

    a, b = digits(on_file), digits(submitted)
    if not a or not b:
        return False
    # Compare last 10 digits for US-style numbers
    return a == b or a.endswith(b[-10:]) or b.endswith(a[-10:])
