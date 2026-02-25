"""Patient details service."""
import json
import os
import logging
from typing import Optional
from app.infrastructure.config.access_control_repo import AccessControlRepository
from app.core.config import settings

logger = logging.getLogger(__name__)


class PatientDetailsService:
    """Service for building role-based patient detail queries."""
    
    def __init__(self, access_control_repo: Optional[AccessControlRepository] = None):
        self.access_control_repo = access_control_repo or AccessControlRepository()
    
    def build_patient_details_sql(self, user_id: str, patient_id: str) -> Optional[str]:
        """
        Uses access_control.json to build a role-based patient detail query.
        
        Args:
            user_id: User ID
            patient_id: Patient ID
            
        Returns:
            SQL query string or None if not allowed
        """
        logger.info(f"🔨 [PATIENT_DETAILS_SQL] Building SQL for user_id={user_id}, patient_id={patient_id}")
        logger.info(f"🔨 [PATIENT_DETAILS_SQL] Database type: {settings.db_type}")
        
        access_data = self.access_control_repo.load()
        logger.debug(f"🔨 [PATIENT_DETAILS_SQL] Loaded access control data, users: {list(access_data.keys())}")
        
        user_cfg = access_data.get(user_id)
        if not user_cfg:
            logger.error(f"❌ [PATIENT_DETAILS_SQL] User {user_id} not found in access control")
            return None
        
        logger.info(f"✅ [PATIENT_DETAILS_SQL] Found user config for {user_id}")
        allowed_schema = user_cfg.get("allowed_schema", {})
        logger.debug(f"🔨 [PATIENT_DETAILS_SQL] Allowed schema has {len(allowed_schema)} tables")
        
        if "ap_patient" not in allowed_schema:
            logger.error(f"❌ [PATIENT_DETAILS_SQL] ap_patient table not in allowed schema")
            return None
        
        logger.info(f"✅ [PATIENT_DETAILS_SQL] ap_patient table is allowed")
        
        select_cols = []
        joins = []
        
        # Select only important patient fields (not all 107 columns)
        # These are the fields actually displayed in the frontend
        important_patient_fields = [
            "key", "patient_mrn", "full_name", "first_name", "last_name",
            "dob", "gender_lkey", "blood_group_lkey",
            "phone_number", "mobile_number", "email",
            "emergency_contact_name", "emergency_contact_phone",
            "patient_class_lkey"
        ]
        
        # ap_patient table columns use 'patients_' prefix (for consistency with old code)
        # The API route will transform these to unprefixed fields for the frontend
        patient_columns = allowed_schema.get("ap_patient", {}).get("columns", [])
        for col in important_patient_fields:
            if col in patient_columns:
                select_cols.append(f"p.{col} AS patients_{col}")
        
        logger.info(f"🔨 [PATIENT_DETAILS_SQL] Selected {len(select_cols)} important patient fields (out of {len(patient_columns)} total)")
        
        # Join encounter for admission/discharge info (get latest encounter)
        # Note: encounter_type_lkey may be NULL in some databases, so we don't filter by it
        # IMPORTANT: Admission date is stored in created_at (millisecond timestamp)
        # Discharge date is discharge_at (millisecond timestamp when encounter is complete)
        if "ap_encounter" in allowed_schema:
            # Join to the latest encounter using a subquery
            # Use database-appropriate boolean syntax
            is_valid_check = "is_valid = TRUE" if settings.db_type == "postgresql" else "is_valid = 1"
            joins.append(f"""
LEFT JOIN (
    SELECT e1.* FROM ap_encounter e1
    INNER JOIN (
        SELECT patient_key, MAX(created_at) as max_date
        FROM ap_encounter
        WHERE {is_valid_check}
        GROUP BY patient_key
    ) e2 ON e1.patient_key = e2.patient_key 
         AND e1.created_at = e2.max_date
         AND e1.{is_valid_check}
) e ON e.patient_key = p.key
""".strip())
            # Select created_at (admission date) and discharge_at (discharge date)
            for col in ["key", "created_at", "discharge_at", "encounter_status_lkey", "encounter_type_lkey"]:
                if col in allowed_schema["ap_encounter"].get("columns", []):
                    # Map created_at to admissions_actual_start_date for frontend compatibility
                    if col == "created_at":
                        select_cols.append(f"e.{col} AS admissions_actual_start_date")
                    else:
                        select_cols.append(f"e.{col} AS admissions_{col}")
        
        # Join diagnoses
        if "ap_patient_diagnose" in allowed_schema:
            is_valid_check = "is_valid = TRUE" if settings.db_type == "postgresql" else "is_valid = 1"
            is_major_check = "is_major = TRUE" if settings.db_type == "postgresql" else "is_major = 1"
            joins.append(f"LEFT JOIN ap_patient_diagnose d ON d.patient_key = p.key AND d.{is_valid_check} AND d.{is_major_check}")
            for col in ["key", "diagnose_code", "description"]:
                if col in allowed_schema["ap_patient_diagnose"].get("columns", []):
                    select_cols.append(f"d.{col} AS patient_details_{col}")
        
        # Join observation summary for vitals (height, weight, BMI)
        # Frontend expects: patient_health_height_cm, patient_health_weight_kg, patient_health_bmi
        if "ap_patient_observation_summary" in allowed_schema:
            is_valid_check = "is_valid = TRUE" if settings.db_type == "postgresql" else "is_valid = 1"
            joins.append(f"LEFT JOIN ap_patient_observation_summary obs ON obs.patient_key = p.key AND obs.{is_valid_check}")
            if "latestheight" in allowed_schema["ap_patient_observation_summary"].get("columns", []):
                select_cols.append("obs.latestheight AS patient_health_height_cm")
            if "latestweight" in allowed_schema["ap_patient_observation_summary"].get("columns", []):
                select_cols.append("obs.latestweight AS patient_health_weight_kg")
            if "latestbmi" in allowed_schema["ap_patient_observation_summary"].get("columns", []):
                select_cols.append("obs.latestbmi AS patient_health_bmi")
            if "last_date" in allowed_schema["ap_patient_observation_summary"].get("columns", []):
                select_cols.append("obs.last_date AS patient_health_last_checkup_date")
        
        # Join allergies (get first allergy or aggregate)
        # Frontend expects: patient_health_allergies
        # Use subquery for aggregation to avoid GROUP BY issues
        if "ap_patient_allergies" in allowed_schema and "ap_allergens" in allowed_schema:
            is_valid_check = "is_valid = TRUE" if settings.db_type == "postgresql" else "is_valid = 1"
            if "allergen_name" in allowed_schema["ap_allergens"].get("columns", []):
                # Use subquery for aggregation to avoid GROUP BY complexity
                if settings.db_type == "postgresql":
                    select_cols.append("""(SELECT STRING_AGG(DISTINCT alg2.allergen_name, ', ')
                    FROM ap_patient_allergies pa2
                    LEFT JOIN ap_allergens alg2 ON alg2.key = pa2.allergy_key AND alg2.is_valid = TRUE
                    WHERE pa2.patient_key = p.key AND pa2.is_valid = TRUE) AS patient_health_allergies""")
                else:
                    joins.append(f"LEFT JOIN ap_patient_allergies pa ON pa.patient_key = p.key AND pa.{is_valid_check}")
                    joins.append(f"LEFT JOIN ap_allergens alg ON alg.key = pa.allergy_key AND alg.{is_valid_check}")
                    select_cols.append("GROUP_CONCAT(DISTINCT alg.allergen_name) AS patient_health_allergies")
        
        # Join insurance
        # Frontend expects: patient_details_insurance_provider
        if "ap_patient_insurance" in allowed_schema:
            is_valid_check = "is_valid = TRUE" if settings.db_type == "postgresql" else "is_valid = 1"
            primary_insurance_check = "primary_insurance = TRUE" if settings.db_type == "postgresql" else "primary_insurance = 1"
            joins.append(f"LEFT JOIN ap_patient_insurance ins ON ins.patient_key = p.key AND ins.{is_valid_check} AND ins.{primary_insurance_check}")
            if "insurance_provider_lkey" in allowed_schema["ap_patient_insurance"].get("columns", []):
                select_cols.append("ins.insurance_provider_lkey AS patient_details_insurance_provider")
        
        # Join social history (smoking, alcohol)
        # Frontend expects: patient_health_smoking_status, patient_health_alcohol_use
        if "ap_patient_social_history" in allowed_schema:
            is_valid_check = "is_valid = TRUE" if settings.db_type == "postgresql" else "is_valid = 1"
            joins.append(f"LEFT JOIN ap_patient_social_history sh ON sh.patient_key = p.key AND sh.{is_valid_check}")
            if "current_smoker" in allowed_schema["ap_patient_social_history"].get("columns", []):
                if settings.db_type == "postgresql":
                    select_cols.append("CASE WHEN sh.current_smoker = TRUE THEN 'Yes' WHEN sh.previous_smoker = TRUE THEN 'Former smoker' ELSE 'No' END AS patient_health_smoking_status")
                else:
                    select_cols.append("CASE WHEN sh.current_smoker = 1 THEN 'Yes' WHEN sh.previous_smoker = 1 THEN 'Former smoker' ELSE 'No' END AS patient_health_smoking_status")
            if "alcohol_consumption" in allowed_schema["ap_patient_social_history"].get("columns", []):
                select_cols.append("sh.alcohol_consumption AS patient_health_alcohol_use")
        
        # Join chronic conditions/problems
        # Frontend expects: patient_health_chronic_conditions
        # Use subquery for aggregation to avoid GROUP BY issues
        if "ap_patient_problems" in allowed_schema:
            is_valid_check = "is_valid = TRUE" if settings.db_type == "postgresql" else "is_valid = 1"
            if "condition" in allowed_schema["ap_patient_problems"].get("columns", []):
                # Use subquery for aggregation to avoid GROUP BY complexity
                if settings.db_type == "postgresql":
                    select_cols.append("""(SELECT STRING_AGG(DISTINCT prob2.condition, ', ')
                    FROM ap_patient_problems prob2
                    WHERE prob2.patient_key = p.key AND prob2.is_valid = TRUE) AS patient_health_chronic_conditions""")
                else:
                    joins.append(f"LEFT JOIN ap_patient_problems prob ON prob.patient_key = p.key AND prob.{is_valid_check}")
                    select_cols.append("GROUP_CONCAT(DISTINCT prob.condition) AS patient_health_chronic_conditions")
        
        select_sql = ",\n  ".join(select_cols) if select_cols else "p.key AS patients_key"
        join_sql = "\n".join(joins)
        
        logger.info(f"🔨 [PATIENT_DETAILS_SQL] Built {len(select_cols)} select columns, {len(joins)} joins")
        
        # Check if we're using aggregation functions in JOINs (not subqueries)
        # Note: For PostgreSQL, we use subqueries for aggregation, so no GROUP BY needed
        uses_aggregation_in_joins = any("GROUP_CONCAT" in col for col in select_cols)
        logger.info(f"🔨 [PATIENT_DETAILS_SQL] Uses aggregation in joins: {uses_aggregation_in_joins}")
        
        # Use database-appropriate boolean syntax
        is_valid_check = "is_valid = TRUE" if settings.db_type == "postgresql" else "is_valid = 1"
        logger.debug(f"🔨 [PATIENT_DETAILS_SQL] Using boolean check: {is_valid_check}")
        
        if uses_aggregation_in_joins:
            # Only SQLite uses GROUP_CONCAT in joins, needs GROUP BY
            sql = f"""
SELECT
  {select_sql}
FROM ap_patient p
{join_sql}
WHERE p.key = '{patient_id}' AND p.{is_valid_check}
GROUP BY p.key
LIMIT 1
""".strip()
        else:
            # PostgreSQL uses subqueries for aggregation, no GROUP BY needed
            sql = f"""
SELECT
  {select_sql}
FROM ap_patient p
{join_sql}
WHERE p.key = '{patient_id}' AND p.{is_valid_check}
LIMIT 1
""".strip()
        
        logger.info(f"✅ [PATIENT_DETAILS_SQL] SQL built successfully ({len(sql)} characters)")
        logger.debug(f"📜 [PATIENT_DETAILS_SQL] Final SQL:\n{sql}")
        return sql


# Global instance
_patient_details_service = PatientDetailsService()


def build_patient_details_sql(user_id: str, patient_id: str) -> Optional[str]:
    """Legacy function for backward compatibility."""
    return _patient_details_service.build_patient_details_sql(user_id, patient_id)

