"""Stub EMR service integration for prescription submission."""
import logging
from typing import Any, Dict, Optional
from app.core.config import settings

logger = logging.getLogger(__name__)


def submit_prescription(
    doctor_user_id: str,
    patient_mrn: str,
    draft_text: str,
    note: Optional[str] = None,
) -> Dict[str, Any]:
    """Submit a prescription to the hospital EMR/pharmacy system.

    This is a stub implementation until the vendor EMR API contract is known.
    Replace with a real EMR integration using `settings.emr_api_base_url`.
    """
    # TODO: fill in EMR API contract
    # Example expected interface:
    # payload = {
    #     "doctor_id": doctor_user_id,
    #     "patient_mrn": patient_mrn,
    #     "prescription_text": draft_text,
    #     "note": note,
    # }
    # if settings.emr_api_base_url:
    #     response = requests.post(
    #         f"{settings.emr_api_base_url}/prescriptions",
    #         json=payload,
    #         headers={"Authorization": f"Bearer {settings.emr_api_key}"},
    #         timeout=30,
    #     )
    #     return response.json()

    logger.info(
        "EMR stub submit_prescription called for doctor=%s patient_mrn=%s",
        doctor_user_id,
        patient_mrn,
    )

    return {
        "status": "submitted",
        "submitted_by": doctor_user_id,
        "patient_mrn": patient_mrn,
        "draft_text": draft_text,
        "note": note,
        "message": "This is a stubbed EMR response. Replace with real EMR API integration.",
    }
