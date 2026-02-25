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
    1. Validate patient_id exists (can be integer ID or string key like 'pat001')
    2. Build role-safe SQL using build_patient_details_sql(user_id, patient_id)
       - reads access_control.json
       - selects only allowed columns
       - adds joins only if allowed
    3. Send that SQL to validator to execute
    4. Return first row as {ok:true, patient:{...}}
    """
    logger.info(f"🔍 [PATIENT_DETAILS] Starting request: user_id={req.user_id}, patient_id={req.patient_id}")
    
    # Validate patient_id exists (can be string key or numeric ID)
    patient_id = str(req.patient_id).strip()
    if not patient_id:
        logger.error(f"❌ [PATIENT_DETAILS] Invalid patient_id: {req.patient_id}")
        raise HTTPException(status_code=400, detail="Invalid patient_id.")
    
    logger.info(f"📋 [PATIENT_DETAILS] Processing patient_id: '{patient_id}'")
    
    interaction_id = _audit_repo.insert_interaction(
        user_id=req.user_id,
        session_id=req.session_id or "no_session",
        role=req.role,
        intent="patient_details",
        approved=True,
        raw_message=f"patient_details patient_id={patient_id}",
        final_message=f"patient_details patient_id={patient_id}",
    )
    logger.info(f"📝 [PATIENT_DETAILS] Created interaction_id: {interaction_id}")
    
    logger.info(f"🔨 [PATIENT_DETAILS] Building SQL for user_id={req.user_id}, patient_id={patient_id}")
    sql = _patient_details_service.build_patient_details_sql(req.user_id, patient_id)
    
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
        logger.warning(f"⚠️ [PATIENT_DETAILS] No rows returned for patient_id={patient_id}")
        logger.warning(f"📜 [PATIENT_DETAILS] SQL that returned no rows:\n{sql}")
        
        # Try to check if patient exists at all
        logger.info(f"🔍 [PATIENT_DETAILS] Checking if patient exists in database...")
        try:
            from app.infrastructure.db.hospital_repo import HospitalRepository
            repo = HospitalRepository()
            check_sql = f"SELECT key, full_name FROM ap_patient WHERE key = '{patient_id}' LIMIT 1"
            logger.info(f"🔍 [PATIENT_DETAILS] Executing check query: {check_sql}")
            check_result = repo.execute_query(check_sql)
            logger.info(f"🔍 [PATIENT_DETAILS] Patient exists check: {len(check_result)} row(s)")
            if check_result:
                logger.info(f"🔍 [PATIENT_DETAILS] Patient found: {check_result[0]}")
            else:
                logger.warning(f"⚠️ [PATIENT_DETAILS] Patient with key '{patient_id}' does not exist in ap_patient table")
        except Exception as e:
            logger.error(f"❌ [PATIENT_DETAILS] Error checking patient existence: {e}", exc_info=True)
        _audit_repo.update_interaction(interaction_id, reply_text="No data found for this patient.", sql_query=sql, row_count=0)
        return PatientDetailsResponse(ok=False, message="No data found for this patient.")
    
    logger.info(f"✅ [PATIENT_DETAILS] Found patient data, processing first row")
    patient = rows[0]
    logger.debug(f"📋 [PATIENT_DETAILS] Raw patient data keys: {list(patient.keys())[:10]}...")  # Log first 10 keys
    
    # Transform field names: remove 'patients_' prefix from patients table columns
    # This matches the frontend expectations (key, full_name, dob instead of patients_key, patients_full_name, patients_dob)
    transformed_patient = {}
    for key, value in patient.items():
        if key.startswith("patients_"):
            # Remove 'patients_' prefix (9 characters: p-a-t-i-e-n-t-s-_)
            new_key = key[9:]  # len("patients_") = 9
            transformed_patient[new_key] = value
        else:
            # Keep other prefixes (patient_details_, patient_health_, admissions_)
            transformed_patient[key] = value
    
    logger.info(f"✅ [PATIENT_DETAILS] Transformed patient data: {len(transformed_patient)} fields")
    logger.debug(f"📋 [PATIENT_DETAILS] Transformed keys: {list(transformed_patient.keys())[:10]}...")  # Log first 10 keys
    
    # Convert millisecond timestamps to readable dates
    # Admission date: created_at (milliseconds) -> admissions_actual_start_date
    # Discharge date: discharge_at (milliseconds) -> admissions_discharge_at
    def convert_millisecond_timestamp(ms_timestamp):
        """Convert millisecond timestamp to ISO date string."""
        if ms_timestamp is None:
            return None
        try:
            # Handle both numeric and string timestamps
            if isinstance(ms_timestamp, str):
                ms_timestamp = float(ms_timestamp)
            # Convert milliseconds to seconds (divide by 1000)
            seconds = float(ms_timestamp) / 1000.0
            from datetime import datetime
            dt = datetime.fromtimestamp(seconds)
            return dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError, OSError) as e:
            logger.warning(f"⚠️ [PATIENT_DETAILS] Failed to convert timestamp {ms_timestamp}: {e}")
            return None
    
    # Convert admission date (created_at)
    if "admissions_actual_start_date" in transformed_patient:
        original_value = transformed_patient["admissions_actual_start_date"]
        converted = convert_millisecond_timestamp(original_value)
        if converted:
            transformed_patient["admissions_actual_start_date"] = converted
            logger.debug(f"🕐 [PATIENT_DETAILS] Converted admission timestamp {original_value} -> {converted}")
    
    # Convert discharge date (discharge_at) - only if not 0 (0 means not discharged)
    if "admissions_discharge_at" in transformed_patient:
        original_value = transformed_patient["admissions_discharge_at"]
        # Check if it's 0 (not discharged) or a valid timestamp
        if original_value and original_value != 0 and str(original_value) != "0":
            converted = convert_millisecond_timestamp(original_value)
            if converted:
                transformed_patient["admissions_discharge_at"] = converted
                logger.debug(f"🕐 [PATIENT_DETAILS] Converted discharge timestamp {original_value} -> {converted}")
        else:
            # Not discharged (discharge_at = 0)
            transformed_patient["admissions_discharge_at"] = None
            logger.debug(f"🕐 [PATIENT_DETAILS] Patient not discharged (discharge_at = {original_value})")
    
    # Save patient_id to session memory in Redis for pronoun resolution ("he", "she", "this patient")
    if req.session_id and req.session_id != "no_session":
        try:
            session = _session_memory.get_session(req.session_id)
            session["last_patient_id"] = patient_id
            patient_name = transformed_patient.get("full_name")
            if patient_name:
                session["last_patient"] = patient_name
            _session_memory.save_session(req.session_id, session)
            logger.info(f"💾 [MEMORY] ✅ Saved to Redis: patient_id={patient_id}, patient_name={patient_name or 'N/A'}, session_id={req.session_id}")
        except Exception as e:
            logger.error(f"❌ [MEMORY] Failed to save to Redis: {e}", exc_info=True)
    
    _audit_repo.update_interaction(interaction_id, reply_text="Patient details returned.", sql_query=sql, row_count=1)
    logger.info(f"✅ [PATIENT_DETAILS] Successfully returning patient details for patient_id={patient_id}")
    return PatientDetailsResponse(ok=True, patient=transformed_patient)

