"""Patient details API routes."""
import logging
from fastapi import APIRouter, HTTPException
from app.models.schemas import PatientDetailsRequest, PatientDetailsResponse
from app.services.patient_details import PatientDetailsService
from app.services.session_memory import SessionMemoryService
from app.infrastructure.db.audit_repo import AuditRepository
from app.infrastructure.http.clients import post_json_logged
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

# Initialize services
_patient_details_service = PatientDetailsService()
_audit_repo = AuditRepository()
_session_memory = SessionMemoryService()


@router.post("/patient_details", response_model=PatientDetailsResponse)
def patient_details(req: PatientDetailsRequest) -> PatientDetailsResponse:
    """
    Get patient details (row-click popup, no LLM).
    
    Steps:
    1. Validate medical_record_number exists
    2. Build role-safe SQL using build_patient_details_sql(user_id, medical_record_number, lookup_field="medical_record_number")
       - reads access_control.json
       - selects only allowed columns
       - adds joins only if allowed
    3. Send that SQL to validator to execute
    4. Return first row as {ok:true, patient:{...}}
    """
    logger.info(
        "🔍 [PATIENT_DETAILS] Starting request: user_id=%s, medical_record_number=%s",
        req.user_id,
        req.medical_record_number,
    )
    
    medical_record_number = str(req.medical_record_number).strip()
    if not medical_record_number:
        logger.error("❌ [PATIENT_DETAILS] Invalid medical_record_number: %s", req.medical_record_number)
        raise HTTPException(status_code=400, detail="Invalid medical_record_number.")
    
    logger.info("📋 [PATIENT_DETAILS] Processing medical_record_number: '%s'", medical_record_number)
    
    interaction_id = _audit_repo.insert_interaction(
        user_id=req.user_id,
        session_id=req.session_id or "no_session",
        role=req.role,
        intent="patient_details",
        approved=True,
        raw_message=f"patient_details medical_record_number={medical_record_number}",
        final_message=f"patient_details medical_record_number={medical_record_number}",
    )
    logger.info(f"📝 [PATIENT_DETAILS] Created interaction_id: {interaction_id}")
    
    logger.info(f"🔨 [PATIENT_DETAILS] Building SQL for user_id={req.user_id} by medical_record_number")
    sql = _patient_details_service.build_patient_details_sql(
        req.user_id,
        medical_record_number,
        lookup_field="medical_record_number",
    )
    
    if not sql:
        logger.error(f"❌ [PATIENT_DETAILS] No SQL generated - user may not have access")
        _audit_repo.update_interaction(interaction_id, ok=False, error="No patient details allowed for this user.")
        raise HTTPException(status_code=403, detail="No patient details allowed for this user.")
    
    logger.info(f"✅ [PATIENT_DETAILS] SQL generated ({len(sql)} chars)")
    logger.info(f"📜 [PATIENT_DETAILS] Generated SQL (first 500 chars):\n{sql[:500]}...")
    logger.debug(f"📜 [PATIENT_DETAILS] Full SQL:\n{sql}")
    
    # Call validator
    logger.info(f"🔍 [PATIENT_DETAILS] Calling validator service at {settings.validator_url}/validate")
    payload = {"user_id": req.user_id, "sql_query": sql}
    ok_val, val_body, err_val = post_json_logged(
        interaction_id,
        "validator",
        f"{settings.validator_url}/validate",
        payload,
        audit_service=_audit_repo,
    )
    
    logger.info(f"📊 [PATIENT_DETAILS] Validator response: ok={ok_val}, error={err_val}")
    
    if not ok_val:
        logger.error(f"❌ [PATIENT_DETAILS] Validation failed: {err_val}")
        _audit_repo.update_interaction(interaction_id, ok=False, error=f"Validation failed: {err_val}", sql_query=sql)
        raise HTTPException(status_code=502, detail=f"Validation failed for patient details query: {err_val}")
    
    validation_result = val_body.get("validation_result", {})
    rows = validation_result.get("rows", [])
    row_count = len(rows)
    
    logger.info(f"📊 [PATIENT_DETAILS] Query returned {row_count} row(s)")
    logger.info(f"📊 [PATIENT_DETAILS] Validation result keys: {list(validation_result.keys())}")
    logger.info(f"📊 [PATIENT_DETAILS] Validation message: {validation_result.get('message', 'N/A')}")
    
    if not rows:
        logger.warning(
            "⚠️ [PATIENT_DETAILS] No rows returned for medical_record_number=%s",
            medical_record_number,
        )
        logger.warning(f"📜 [PATIENT_DETAILS] SQL that returned no rows:\n{sql}")
        
        # Try to check if patient exists at all
        logger.info(f"🔍 [PATIENT_DETAILS] Checking if patient exists in database...")
        try:
            from app.infrastructure.db.hospital_repo import HospitalRepository
            repo = HospitalRepository()
            safe_mrn = medical_record_number.replace("'", "''")
            check_sql = (
                "SELECT medical_record_number, TRIM(COALESCE(first_name, '') || ' ' || COALESCE(second_name, '') || "
                "COALESCE(' ' || third_name, '') || ' ' || COALESCE(last_name, '')) AS full_name "
                f"FROM patients WHERE CAST(medical_record_number AS TEXT) = '{safe_mrn}' LIMIT 1"
            )
            logger.info(f"🔍 [PATIENT_DETAILS] Executing check query: {check_sql}")
            check_result = repo.execute_query(check_sql)
            logger.info(f"🔍 [PATIENT_DETAILS] Patient exists check: {len(check_result)} row(s)")
            if check_result:
                logger.info(f"🔍 [PATIENT_DETAILS] Patient found: {check_result[0]}")
            else:
                logger.warning(
                    "⚠️ [PATIENT_DETAILS] Patient with MRN '%s' does not exist in patients table",
                    medical_record_number,
                )
        except Exception as e:
            logger.error(f"❌ [PATIENT_DETAILS] Error checking patient existence: {e}", exc_info=True)
        _audit_repo.update_interaction(interaction_id, reply_text="No data found for this patient.", sql_query=sql, row_count=0)
        return PatientDetailsResponse(ok=False, message="No data found for this patient.")
    
    logger.info(f"✅ [PATIENT_DETAILS] Found patient data, processing first row")
    patient = rows[0]
    logger.debug(f"📋 [PATIENT_DETAILS] Raw patient data keys: {list(patient.keys())[:10]}...")  # Log first 10 keys

    transformed_patient = _patient_details_service.transform_patient_data(patient)
    logger.info(f"✅ [PATIENT_DETAILS] Transformed patient data: {len(transformed_patient)} fields")
    logger.debug(f"📋 [PATIENT_DETAILS] Transformed keys: {list(transformed_patient.keys())[:10]}...")  # Log first 10 keys
    
    # Save MRN to session memory in Redis for pronoun resolution ("he", "she", "this patient")
    if req.session_id and req.session_id != "no_session":
        try:
            session = _session_memory.get_session(req.session_id)
            session["last_patient_mrn"] = medical_record_number
            patient_name = transformed_patient.get("full_name")
            if patient_name:
                session["last_patient"] = patient_name
            _session_memory.save_session(req.session_id, session)
            logger.info(
                "💾 [MEMORY] ✅ Saved to Redis: medical_record_number=%s, patient_name=%s, session_id=%s",
                medical_record_number,
                patient_name or "N/A",
                req.session_id,
            )
        except Exception as e:
            logger.error(f"❌ [MEMORY] Failed to save to Redis: {e}", exc_info=True)
    
    _audit_repo.update_interaction(interaction_id, reply_text="Patient details returned.", sql_query=sql, row_count=1)
    logger.info(
        "✅ [PATIENT_DETAILS] Successfully returning patient details for medical_record_number=%s",
        medical_record_number,
    )
    return PatientDetailsResponse(ok=True, patient=transformed_patient)

