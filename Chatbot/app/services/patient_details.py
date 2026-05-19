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

    SECTION_TABLES = {
        "demographics": {"patients"},
        "contact": {"patients"},
        "address": {"address"},
        "preferences": {"patients"},
        "diagnosis": {"patient_diagnoses", "icd_diagnosis"},
        "allergies": {"patient_allergies", "allergens"},
        "vitals": {"vital_signs"},
        "insurance": {"patient_insurances", "payor"},
        "social history": {"social_history"},
        "chronic conditions": {"patient_problems"},
    }

    SECTION_FIELDS = {
        "demographics": [
            "medical_record_number", "full_name", "first_name", "second_name",
            "third_name", "last_name", "date_of_birth", "sex_at_birth",
            "patient_classes", "is_verified", "is_completed_patient",
        ],
        "contact": [
            "primary_mobile_number", "second_mobile_number", "home_phone",
            "work_phone", "email",
            "emergency_contact_name", "emergency_contact_phone",
        ],
        "address": [
            "address_street_name", "address_house_apartment_number",
            "address_additional_address_line", "address_postal_zip_code",
        ],
        "preferences": [
            "receive_sms", "receive_email", "preferred_way_of_contact",
            "native_language", "role",
        ],
        "diagnosis": [
            "patient_details_diagnose_code", "patient_details_description",
            "patient_details_diagnosis_type", "patient_details_diagnosis_created_date",
        ],
        "allergies": [
            "patient_health_allergies", "patient_health_allergy_severity",
            "patient_health_allergy_note",
        ],
        "vitals": [
            "patient_health_blood_pressure", "patient_health_heart_rate",
            "patient_health_temperature", "patient_health_oxygen_saturation",
            "patient_health_respiratory_rate", "patient_health_last_checkup_date",
        ],
        "insurance": [
            "patient_details_insurance_provider", "patient_details_policy_number",
            "patient_details_group_number", "patient_details_expiration_date",
        ],
        "social history": [
            "patient_health_smoking_status", "patient_health_alcohol_use",
            "patient_health_substance_use",
        ],
        "chronic conditions": [
            "patient_health_chronic_conditions", "patient_health_reason_of_visit",
            "patient_health_patient_conditions", "patient_health_functional_status",
        ],
    }
    
    def __init__(self, access_control_repo: Optional[AccessControlRepository] = None):
        self.access_control_repo = access_control_repo or AccessControlRepository()

    def _escape_sql_literal(self, value: str) -> str:
        """Escape a SQL string literal safely for inline read-only queries."""
        return str(value).replace("'", "''")

    def _build_full_name_expr(self, alias: str) -> str:
        """Build a cross-database full-name expression for the patients table."""
        return (
            f"TRIM(COALESCE({alias}.first_name, '') || ' ' || "
            f"COALESCE({alias}.second_name, '') || ' ' || "
            f"COALESCE({alias}.third_name, '') || ' ' || "
            f"COALESCE({alias}.last_name, ''))"
        )

    def _build_patients_table_sql(
        self,
        allowed_schema: dict,
        patient_identifier: str,
        lookup_field: str = "id",
    ) -> str:
        """Build patient detail SQL using the newer patients-centric schema."""
        safe_identifier = self._escape_sql_literal(patient_identifier)
        select_cols = []
        joins = []
        patient_columns = allowed_schema.get("patients", {}).get("columns", [])

        if "medical_record_number" in patient_columns:
            select_cols.append("p.medical_record_number AS patients_medical_record_number")
        if {"first_name", "last_name"}.issubset(set(patient_columns)):
            select_cols.append(f"{self._build_full_name_expr('p')} AS patients_full_name")
        if "first_name" in patient_columns:
            select_cols.append("p.first_name AS patients_first_name")
        if "second_name" in patient_columns:
            select_cols.append("p.second_name AS patients_second_name")
        if "third_name" in patient_columns:
            select_cols.append("p.third_name AS patients_third_name")
        if "last_name" in patient_columns:
            select_cols.append("p.last_name AS patients_last_name")
        if "date_of_birth" in patient_columns:
            select_cols.append("p.date_of_birth AS patients_date_of_birth")
        if "sex_at_birth" in patient_columns:
            select_cols.append("p.sex_at_birth AS patients_sex_at_birth")
        if "patient_classes" in patient_columns:
            select_cols.append("p.patient_classes AS patients_patient_classes")
        if "is_private_patient" in patient_columns:
            select_cols.append("p.is_private_patient AS patients_is_private_patient")
        if "receive_sms" in patient_columns:
            select_cols.append("p.receive_sms AS patients_receive_sms")
        if "receive_email" in patient_columns:
            select_cols.append("p.receive_email AS patients_receive_email")
        if "preferred_way_of_contact" in patient_columns:
            select_cols.append("p.preferred_way_of_contact AS patients_preferred_way_of_contact")
        if "native_language" in patient_columns:
            select_cols.append("p.native_language AS patients_native_language")
        if "home_phone" in patient_columns:
            select_cols.append("p.home_phone AS patients_home_phone")
        if "primary_mobile_number" in patient_columns:
            select_cols.append("p.primary_mobile_number AS patients_primary_mobile_number")
        if "second_mobile_number" in patient_columns:
            select_cols.append("p.second_mobile_number AS patients_second_mobile_number")
        if "work_phone" in patient_columns:
            select_cols.append("p.work_phone AS patients_work_phone")
        if "email" in patient_columns:
            select_cols.append("p.email AS patients_email")
        if "emergency_contact_name" in patient_columns:
            select_cols.append("p.emergency_contact_name AS patients_emergency_contact_name")
        if "emergency_contact_relation" in patient_columns:
            select_cols.append("p.emergency_contact_relation AS patients_emergency_contact_relation")
        if "emergency_contact_phone" in patient_columns:
            select_cols.append("p.emergency_contact_phone AS patients_emergency_contact_phone")
        if "role" in patient_columns:
            select_cols.append("p.role AS patients_role")
        if "marital_status" in patient_columns:
            select_cols.append("p.marital_status AS patients_marital_status")
        if "nationality" in patient_columns:
            select_cols.append("p.nationality AS patients_nationality")
        if "religion" in patient_columns:
            select_cols.append("p.religion AS patients_religion")
        if "ethnicity" in patient_columns:
            select_cols.append("p.ethnicity AS patients_ethnicity")
        if "occupation" in patient_columns:
            select_cols.append("p.occupation AS patients_occupation")
        if "responsible_party" in patient_columns:
            select_cols.append("p.responsible_party AS patients_responsible_party")
        if "educational_level" in patient_columns:
            select_cols.append("p.educational_level AS patients_educational_level")
        if "previous_id" in patient_columns:
            select_cols.append("p.previous_id AS patients_previous_id")
        if "archiving_number" in patient_columns:
            select_cols.append("p.archiving_number AS patients_archiving_number")
        if "details" in patient_columns:
            select_cols.append("p.details AS patients_details")
        if "is_unknown" in patient_columns:
            select_cols.append("p.is_unknown AS patients_is_unknown")
        if "is_verified" in patient_columns:
            select_cols.append("p.is_verified AS patients_is_verified")
        if "is_completed_patient" in patient_columns:
            select_cols.append("p.is_completed_patient AS patients_is_completed_patient")
        if "created_date" in patient_columns:
            select_cols.append("p.created_date AS patients_created_date")
        if "last_modified_date" in patient_columns:
            select_cols.append("p.last_modified_date AS patients_last_modified_date")

        if "address" in allowed_schema:
            joins.append(
                """
LEFT JOIN address addr ON addr.id = (
    SELECT a2.id
    FROM address a2
    WHERE a2.patient_id = p.id
    ORDER BY CASE WHEN COALESCE(a2.is_current, FALSE) THEN 0 ELSE 1 END, a2.id DESC
    LIMIT 1
)
""".strip()
            )
            address_columns = allowed_schema["address"].get("columns", [])
            if "street_name" in address_columns:
                select_cols.append("addr.street_name AS address_street_name")
            if "house_apartment_number" in address_columns:
                select_cols.append("addr.house_apartment_number AS address_house_apartment_number")
            if "additional_address_line" in address_columns:
                select_cols.append("addr.additional_address_line AS address_additional_address_line")
            if "postal_zip_code" in address_columns:
                select_cols.append("addr.postal_zip_code AS address_postal_zip_code")
            if "location_json" in address_columns:
                select_cols.append("addr.location_json AS address_location_json")

        if "patient_diagnoses" in allowed_schema and "icd_diagnosis" in allowed_schema:
            diagnosis_order = "ORDER BY pd.major DESC, pd.created_date DESC, pd.id DESC"
            select_cols.append(
                f"""(SELECT COALESCE(diag.icd_code, diag.icd_coding)
                    FROM patient_diagnoses pd
                    LEFT JOIN icd_diagnosis diag ON diag.id = pd.diagnosis_id
                    WHERE pd.patient_id = p.id
                    {diagnosis_order}
                    LIMIT 1) AS patient_details_diagnose_code"""
            )
            select_cols.append(
                f"""(SELECT COALESCE(diag.icd_full_description, diag.icd_short_description, diag.icd_code, diag.icd_coding)
                    FROM patient_diagnoses pd
                    LEFT JOIN icd_diagnosis diag ON diag.id = pd.diagnosis_id
                    WHERE pd.patient_id = p.id
                    {diagnosis_order}
                    LIMIT 1) AS patient_details_description"""
            )
            select_cols.append(
                f"""(SELECT pd.type
                    FROM patient_diagnoses pd
                    WHERE pd.patient_id = p.id
                    {diagnosis_order}
                    LIMIT 1) AS patient_details_diagnosis_type"""
            )
            select_cols.append(
                f"""(SELECT pd.created_date
                    FROM patient_diagnoses pd
                    WHERE pd.patient_id = p.id
                    {diagnosis_order}
                    LIMIT 1) AS patient_details_diagnosis_created_date"""
            )

        if "patient_allergies" in allowed_schema and "allergens" in allowed_schema:
            allergy_expr = (
                "STRING_AGG(DISTINCT alg.name, ', ')" if settings.db_type == "postgresql"
                else "GROUP_CONCAT(DISTINCT alg.name)"
            )
            select_cols.append(
                f"""(SELECT {allergy_expr}
                    FROM patient_allergies pa
                    LEFT JOIN allergens alg ON alg.id = pa.allergen_id
                    WHERE pa.patient_id = p.id) AS patient_health_allergies"""
            )
            select_cols.append(
                """(SELECT pa.severity
                    FROM patient_allergies pa
                    WHERE pa.patient_id = p.id
                    ORDER BY pa.created_date DESC, pa.id DESC
                    LIMIT 1) AS patient_health_allergy_severity"""
            )
            select_cols.append(
                """(SELECT COALESCE(pa.note, pa.allergic_reactions)
                    FROM patient_allergies pa
                    WHERE pa.patient_id = p.id
                    ORDER BY pa.created_date DESC, pa.id DESC
                    LIMIT 1) AS patient_health_allergy_note"""
            )

        if "patient_problems" in allowed_schema:
            problems_expr = (
                "STRING_AGG(DISTINCT prob.condition, ', ')" if settings.db_type == "postgresql"
                else "GROUP_CONCAT(DISTINCT prob.condition)"
            )
            select_cols.append(
                f"""(SELECT {problems_expr}
                    FROM patient_problems prob
                    WHERE prob.patient_id = p.id) AS patient_health_chronic_conditions"""
            )
            select_cols.append(
                """(SELECT prob.status
                    FROM patient_problems prob
                    WHERE prob.patient_id = p.id
                    ORDER BY prob.created_date DESC, prob.id DESC
                    LIMIT 1) AS patient_health_problem_status"""
            )

        if "social_history" in allowed_schema:
            smoking_true = "TRUE" if settings.db_type == "postgresql" else "1"
            prev_true = "TRUE" if settings.db_type == "postgresql" else "1"
            select_cols.append(
                f"""(SELECT CASE
                        WHEN sh.is_current_smoker = {smoking_true} THEN 'Yes'
                        WHEN sh.is_previous_smoker = {prev_true} THEN 'Former smoker'
                        ELSE 'No'
                    END
                    FROM social_history sh
                    WHERE sh.patient_id = p.id
                    ORDER BY sh.id DESC
                    LIMIT 1) AS patient_health_smoking_status"""
            )
            select_cols.append(
                """(SELECT sh.alcohol_consumption
                    FROM social_history sh
                    WHERE sh.patient_id = p.id
                    ORDER BY sh.id DESC
                    LIMIT 1) AS patient_health_alcohol_use"""
            )
            select_cols.append(
                """(SELECT sh.substance_use
                    FROM social_history sh
                    WHERE sh.patient_id = p.id
                    ORDER BY sh.id DESC
                    LIMIT 1) AS patient_health_substance_use"""
            )
            select_cols.append(
                """(SELECT sh.physical_limitation
                    FROM social_history sh
                    WHERE sh.patient_id = p.id
                    ORDER BY sh.id DESC
                    LIMIT 1) AS patient_health_physical_limitation"""
            )

        if "patient_insurances" in allowed_schema and "payor" in allowed_schema:
            select_cols.append(
                """(SELECT pay.name
                    FROM patient_insurances pi
                    LEFT JOIN payor pay ON pay.id = pi.payor_id
                    WHERE pi.patient_id = p.id
                    ORDER BY pi.is_primary DESC, pi.id DESC
                    LIMIT 1) AS patient_details_insurance_provider"""
            )
            select_cols.append(
                """(SELECT pi.policy_number
                    FROM patient_insurances pi
                    WHERE pi.patient_id = p.id
                    ORDER BY pi.is_primary DESC, pi.id DESC
                    LIMIT 1) AS patient_details_policy_number"""
            )
            select_cols.append(
                """(SELECT pi.group_number
                    FROM patient_insurances pi
                    WHERE pi.patient_id = p.id
                    ORDER BY pi.is_primary DESC, pi.id DESC
                    LIMIT 1) AS patient_details_group_number"""
            )
            select_cols.append(
                """(SELECT pi.expiration_date
                    FROM patient_insurances pi
                    WHERE pi.patient_id = p.id
                    ORDER BY pi.is_primary DESC, pi.id DESC
                    LIMIT 1) AS patient_details_expiration_date"""
            )
            select_cols.append(
                """(SELECT pi.remaining_benefits
                    FROM patient_insurances pi
                    WHERE pi.patient_id = p.id
                    ORDER BY pi.is_primary DESC, pi.id DESC
                    LIMIT 1) AS patient_details_remaining_benefits"""
            )
            select_cols.append(
                """(SELECT pi.remaining_deductibles
                    FROM patient_insurances pi
                    WHERE pi.patient_id = p.id
                    ORDER BY pi.is_primary DESC, pi.id DESC
                    LIMIT 1) AS patient_details_remaining_deductibles"""
            )

        if "vital_signs" in allowed_schema:
            select_cols.append(
                """(SELECT COALESCE(CAST(vs.blood_pressure_systolic AS TEXT), '') || '/' || COALESCE(CAST(vs.blood_pressure_diastolic AS TEXT), '')
                    FROM vital_signs vs
                    WHERE vs.patient_id = p.id
                    ORDER BY vs.created_date DESC, vs.id DESC
                    LIMIT 1) AS patient_health_blood_pressure"""
            )
            select_cols.append(
                """(SELECT vs.heart_rate
                    FROM vital_signs vs
                    WHERE vs.patient_id = p.id
                    ORDER BY vs.created_date DESC, vs.id DESC
                    LIMIT 1) AS patient_health_heart_rate"""
            )
            select_cols.append(
                """(SELECT vs.temperature
                    FROM vital_signs vs
                    WHERE vs.patient_id = p.id
                    ORDER BY vs.created_date DESC, vs.id DESC
                    LIMIT 1) AS patient_health_temperature"""
            )
            select_cols.append(
                """(SELECT vs.oxygen_saturation
                    FROM vital_signs vs
                    WHERE vs.patient_id = p.id
                    ORDER BY vs.created_date DESC, vs.id DESC
                    LIMIT 1) AS patient_health_oxygen_saturation"""
            )
            select_cols.append(
                """(SELECT vs.respiratory_rate
                    FROM vital_signs vs
                    WHERE vs.patient_id = p.id
                    ORDER BY vs.created_date DESC, vs.id DESC
                    LIMIT 1) AS patient_health_respiratory_rate"""
            )
            select_cols.append(
                """(SELECT vs.notes
                    FROM vital_signs vs
                    WHERE vs.patient_id = p.id
                    ORDER BY vs.created_date DESC, vs.id DESC
                    LIMIT 1) AS patient_health_vitals_note"""
            )
            select_cols.append(
                """(SELECT COALESCE(CAST(vs.last_modified_date AS TEXT), CAST(vs.created_date AS TEXT))
                    FROM vital_signs vs
                    WHERE vs.patient_id = p.id
                    ORDER BY vs.created_date DESC, vs.id DESC
                    LIMIT 1) AS patient_health_last_checkup_date"""
            )

        if "patient_observations_complaints" in allowed_schema:
            select_cols.append(
                """(SELECT poc.patient_conditions
                    FROM patient_observations_complaints poc
                    WHERE poc.patient_id = p.id
                    ORDER BY poc.id DESC
                    LIMIT 1) AS patient_health_notes"""
            )
            select_cols.append(
                """(SELECT poc.reason_of_visit
                    FROM patient_observations_complaints poc
                    WHERE poc.patient_id = p.id
                    ORDER BY poc.id DESC
                    LIMIT 1) AS patient_health_reason_of_visit"""
            )
            select_cols.append(
                """(SELECT poc.patient_conditions
                    FROM patient_observations_complaints poc
                    WHERE poc.patient_id = p.id
                    ORDER BY poc.id DESC
                    LIMIT 1) AS patient_health_patient_conditions"""
            )
            select_cols.append(
                """(SELECT poc.functional_status
                    FROM patient_observations_complaints poc
                    WHERE poc.patient_id = p.id
                    ORDER BY poc.id DESC
                    LIMIT 1) AS patient_health_functional_status"""
            )
            select_cols.append(
                """(SELECT poc.cognitive_check
                    FROM patient_observations_complaints poc
                    WHERE poc.patient_id = p.id
                    ORDER BY poc.id DESC
                    LIMIT 1) AS patient_health_cognitive_check"""
            )

        select_sql = (
            ",\n  ".join(select_cols) if select_cols else "NULL AS patients_medical_record_number"
        )
        join_sql = "\n".join(joins)
        where_clause = (
            f"CAST(p.medical_record_number AS TEXT) = '{safe_identifier}'"
            if lookup_field == "medical_record_number"
            else f"CAST(p.id AS TEXT) = '{safe_identifier}'"
        )
        sql = f"""
SELECT
  {select_sql}
FROM patients p
{join_sql}
WHERE {where_clause}
LIMIT 1
""".strip()
        logger.info("✅ [PATIENT_DETAILS_SQL] Built patients-table SQL successfully (%s characters)", len(sql))
        logger.debug("📜 [PATIENT_DETAILS_SQL] Patients-table SQL:\n%s", sql)
        return sql
    
    def build_patient_details_sql(
        self,
        user_id: str,
        patient_id: str,
        lookup_field: str = "id",
    ) -> Optional[str]:
        """
        Uses access_control.json to build a role-based patient detail query.
        
        Args:
            user_id: User ID
            patient_id: Patient identifier (prefer MRN)
            
        Returns:
            SQL query string or None if not allowed
        """
        logger.info(
            "🔨 [PATIENT_DETAILS_SQL] Building SQL for user_id=%s, identifier=%s, lookup_field=%s",
            user_id,
            patient_id,
            lookup_field,
        )
        logger.info(f"🔨 [PATIENT_DETAILS_SQL] Database type: {settings.db_type}")
        
        user_cfg = self.access_control_repo.get_user_access(user_id)
        if not user_cfg:
            logger.error(f"❌ [PATIENT_DETAILS_SQL] User {user_id} not found in access control")
            return None
        
        logger.info(f"✅ [PATIENT_DETAILS_SQL] Found user config for {user_id}")
        allowed_schema = user_cfg.get("allowed_schema", {})
        logger.debug(f"🔨 [PATIENT_DETAILS_SQL] Allowed schema has {len(allowed_schema)} tables")

        if "patients" in allowed_schema:
            logger.info("✅ [PATIENT_DETAILS_SQL] Using patients table as the patient source")
            return self._build_patients_table_sql(allowed_schema, patient_id, lookup_field=lookup_field)
        
        if "ap_patient" not in allowed_schema:
            logger.error(f"❌ [PATIENT_DETAILS_SQL] ap_patient table not in allowed schema")
            return None
        
        logger.info(f"✅ [PATIENT_DETAILS_SQL] ap_patient table is allowed")
        
        select_cols = []
        joins = []
        
        # Select only important patient fields (not all 107 columns)
        # These are the fields actually displayed in the frontend
        important_patient_fields = [
            "patient_mrn", "full_name", "first_name", "last_name",
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
        
        select_sql = ",\n  ".join(select_cols) if select_cols else "NULL AS patients_patient_mrn"
        join_sql = "\n".join(joins)
        
        logger.info(f"🔨 [PATIENT_DETAILS_SQL] Built {len(select_cols)} select columns, {len(joins)} joins")
        
        # Check if we're using aggregation functions in JOINs (not subqueries)
        # Note: For PostgreSQL, we use subqueries for aggregation, so no GROUP BY needed
        uses_aggregation_in_joins = any("GROUP_CONCAT" in col for col in select_cols)
        logger.info(f"🔨 [PATIENT_DETAILS_SQL] Uses aggregation in joins: {uses_aggregation_in_joins}")
        
        # Use database-appropriate boolean syntax
        is_valid_check = "is_valid = TRUE" if settings.db_type == "postgresql" else "is_valid = 1"
        logger.debug(f"🔨 [PATIENT_DETAILS_SQL] Using boolean check: {is_valid_check}")
        
        safe_identifier = self._escape_sql_literal(patient_id)
        where_clause = (
            f"CAST(p.patient_mrn AS TEXT) = '{safe_identifier}'"
            if lookup_field == "medical_record_number"
            else f"CAST(p.key AS TEXT) = '{safe_identifier}'"
        )

        if uses_aggregation_in_joins:
            # Only SQLite uses GROUP_CONCAT in joins, needs GROUP BY
            sql = f"""
 SELECT
   {select_sql}
 FROM ap_patient p
 {join_sql}
 WHERE {where_clause} AND p.{is_valid_check}
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
 WHERE {where_clause} AND p.{is_valid_check}
 LIMIT 1
 """.strip()
        
        logger.info(f"✅ [PATIENT_DETAILS_SQL] SQL built successfully ({len(sql)} characters)")
        logger.debug(f"📜 [PATIENT_DETAILS_SQL] Final SQL:\n{sql}")
        return sql

    def transform_patient_data(self, patient: dict) -> dict:
        """Normalize patient-details row for frontend/chat responses."""
        transformed_patient = {}
        for key, value in (patient or {}).items():
            if key.startswith("patients_"):
                transformed_patient[key[9:]] = value
            else:
                transformed_patient[key] = value

        def convert_millisecond_timestamp(ms_timestamp):
            if ms_timestamp is None:
                return None
            try:
                if isinstance(ms_timestamp, str):
                    ms_timestamp = float(ms_timestamp)
                seconds = float(ms_timestamp) / 1000.0
                from datetime import datetime
                dt = datetime.fromtimestamp(seconds)
                return dt.strftime("%Y-%m-%d")
            except (ValueError, TypeError, OSError):
                return None

        if "admissions_actual_start_date" in transformed_patient:
            converted = convert_millisecond_timestamp(
                transformed_patient["admissions_actual_start_date"]
            )
            if converted:
                transformed_patient["admissions_actual_start_date"] = converted

        if "admissions_discharge_at" in transformed_patient:
            original_value = transformed_patient["admissions_discharge_at"]
            if original_value and original_value != 0 and str(original_value) != "0":
                converted = convert_millisecond_timestamp(original_value)
                if converted:
                    transformed_patient["admissions_discharge_at"] = converted
            else:
                transformed_patient["admissions_discharge_at"] = None

        for key in (
            "id",
            "patient_id",
            "patients_id",
            "patientid",
            "key",
            "patient_key",
        ):
            transformed_patient.pop(key, None)

        return transformed_patient

    def get_available_sections(self, patient: dict) -> list[str]:
        """Return high-level categories available for a transformed patient profile."""
        available = []
        for section, fields in self.SECTION_FIELDS.items():
            if any(patient.get(field) not in (None, "", [], {}, "null", "undefined") for field in fields):
                available.append(section)
        return available

    def get_supported_sections_for_user(self, user_id: str) -> list[str]:
        """Return high-level patient detail categories allowed for the user's schema."""
        user_cfg = self.access_control_repo.get_user_access(user_id) or {}
        allowed_schema = set((user_cfg.get("allowed_schema") or {}).keys())
        supported = []
        for section, required_tables in self.SECTION_TABLES.items():
            if required_tables.issubset(allowed_schema):
                supported.append(section)
        return supported


# Global instance
_patient_details_service = PatientDetailsService()


def build_patient_details_sql(user_id: str, patient_id: str) -> Optional[str]:
    """Legacy function for backward compatibility."""
    return _patient_details_service.build_patient_details_sql(user_id, patient_id)

