"""Patient-record retrieval for clinician-support/advice flows.

All external lookups are keyed by MRN (Medical Record Number). If the database
requires an internal key/id for joins, this service maps MRN -> internal row
first, but keeps MRN as the external identifier throughout the chatbot flow.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.infrastructure.config.access_control_repo import AccessControlRepository
from app.infrastructure.db.hospital_repo import HospitalRepository
from app.services.patient_details import PatientDetailsService
from app.services.mrn import normalize_mrn

logger = logging.getLogger(__name__)


def _escape_sql_literal(value: str) -> str:
    return str(value or "").replace("'", "''")


def _normalize_ts(value: Any) -> Any:
    """Convert millisecond/second epoch timestamps to YYYY-MM-DD where possible."""
    if value is None or value == "":
        return None

    if isinstance(value, str):
        v = value.strip()
        if not v:
            return None
        # Already a date-like string.
        if len(v) >= 10 and v[4:5] == "-" and v[7:8] == "-":
            return v[:10]
        try:
            # Numeric string?
            value = float(v)
        except Exception:
            return v

    if isinstance(value, (int, float)):
        ts = float(value)
        # Heuristic: > 1e11 => ms; > 1e9 => seconds
        if ts > 1e11:
            ts = ts / 1000.0
        if ts > 1e9:
            try:
                return datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
            except Exception:
                return value

    return value


@dataclass(frozen=True)
class PatientRecord:
    """Structured patient context for clinician-support/advice reasoning."""

    mrn: str
    demographics: Dict[str, Any]
    vitals: List[Dict[str, Any]]
    labs: List[Dict[str, Any]]
    medications: List[Dict[str, Any]]
    allergies: List[Dict[str, Any]]
    visit_history: List[Dict[str, Any]]
    diagnoses: List[Dict[str, Any]]


class PatientRecordService:
    """Fetch structured patient record by MRN for advice-related flows."""

    def __init__(
        self,
        *,
        hospital_repo: Optional[HospitalRepository] = None,
        access_control_repo: Optional[AccessControlRepository] = None,
        patient_details_service: Optional[PatientDetailsService] = None,
    ):
        self.hospital_repo = hospital_repo or HospitalRepository()
        self.access_control_repo = access_control_repo or AccessControlRepository()
        self.patient_details_service = patient_details_service or PatientDetailsService()

    def get_patient_record_by_mrn(self, user_id: str, mrn: str) -> Optional[PatientRecord]:
        mrn_norm = normalize_mrn(mrn)
        if not mrn_norm:
            return None

        user_cfg = self.access_control_repo.get_user_access(user_id) or {}
        allowed_schema = user_cfg.get("allowed_schema") or {}
        if not isinstance(allowed_schema, dict):
            allowed_schema = {}

        # Base profile (demographics + some charted data) via PatientDetailsService, keyed by MRN.
        base_sql = self.patient_details_service.build_patient_details_sql(
            user_id=user_id,
            patient_id=mrn_norm,
            lookup_field="medical_record_number",
        )
        if not base_sql:
            logger.warning("No allowed patient-details SQL for user_id=%s", user_id)
            return None

        try:
            base_rows = self.hospital_repo.execute_query(base_sql)
        except Exception as e:
            logger.warning("Failed to fetch base patient details for MRN=%s: %s", mrn_norm, e)
            return None

        if not base_rows:
            return None

        base_profile = self.patient_details_service.transform_patient_data(base_rows[0])

        demographics = {
            "mrn": mrn_norm,
            "full_name": base_profile.get("full_name") or base_profile.get("patients_full_name"),
            "first_name": base_profile.get("first_name"),
            "second_name": base_profile.get("second_name"),
            "third_name": base_profile.get("third_name"),
            "last_name": base_profile.get("last_name"),
            "date_of_birth": base_profile.get("date_of_birth") or base_profile.get("dob"),
            "sex_at_birth": base_profile.get("sex_at_birth") or base_profile.get("gender_lkey"),
        }

        ap_patient_key = self._fetch_ap_patient_key_if_available(allowed_schema, mrn_norm)
        patient_id = self._fetch_patients_id_if_available(allowed_schema, mrn_norm)

        vitals = self._fetch_vitals(allowed_schema, patient_id=patient_id, mrn=mrn_norm)
        labs = self._fetch_labs(allowed_schema, ap_patient_key=ap_patient_key)
        medications = self._fetch_medications(allowed_schema, ap_patient_key=ap_patient_key)
        allergies = self._fetch_allergies(allowed_schema, ap_patient_key=ap_patient_key, base_profile=base_profile)
        visit_history = self._fetch_visit_history(allowed_schema, ap_patient_key=ap_patient_key)
        diagnoses = self._fetch_diagnoses(allowed_schema, ap_patient_key=ap_patient_key)

        return PatientRecord(
            mrn=mrn_norm,
            demographics=demographics,
            vitals=vitals,
            labs=labs,
            medications=medications,
            allergies=allergies,
            visit_history=visit_history,
            diagnoses=diagnoses,
        )

    def _fetch_ap_patient_key_if_available(self, allowed_schema: Dict[str, Any], mrn: str) -> Optional[str]:
        if "ap_patient" not in allowed_schema:
            return None
        safe = _escape_sql_literal(mrn)
        sql = (
            "SELECT key FROM ap_patient "
            f"WHERE CAST(patient_mrn AS TEXT) = '{safe}' AND is_valid = 1 "
            "LIMIT 1"
        )
        try:
            rows = self.hospital_repo.execute_query(sql)
            if rows and rows[0].get("key") not in (None, ""):
                return str(rows[0]["key"])
        except Exception:
            return None
        return None

    def _fetch_patients_id_if_available(self, allowed_schema: Dict[str, Any], mrn: str) -> Optional[str]:
        if "patients" not in allowed_schema:
            return None
        safe = _escape_sql_literal(mrn)
        sql = (
            "SELECT id FROM patients "
            f"WHERE CAST(medical_record_number AS TEXT) = '{safe}' "
            "LIMIT 1"
        )
        try:
            rows = self.hospital_repo.execute_query(sql)
            if rows and rows[0].get("id") not in (None, ""):
                return str(rows[0]["id"])
        except Exception:
            return None
        return None

    def _fetch_vitals(self, allowed_schema: Dict[str, Any], *, patient_id: Optional[str], mrn: str) -> List[Dict[str, Any]]:
        if not patient_id or "vital_signs" not in allowed_schema:
            return []
        cols = set((allowed_schema.get("vital_signs") or {}).get("columns", []))
        select_cols = []
        for c in [
            "created_date",
            "blood_pressure_systolic",
            "blood_pressure_diastolic",
            "heart_rate",
            "temperature",
            "oxygen_saturation",
            "respiratory_rate",
            "measurement_site",
            "notes",
            "is_triage",
        ]:
            if c in cols:
                select_cols.append(c)

        if not select_cols:
            return []

        pid_safe = _escape_sql_literal(patient_id)
        sql = (
            "SELECT "
            + ", ".join(f"vs.{c} AS {c}" for c in select_cols)
            + " FROM vital_signs vs "
            f"WHERE CAST(vs.patient_id AS TEXT) = '{pid_safe}' "
            "ORDER BY vs.created_date DESC LIMIT 10"
        )
        try:
            rows = self.hospital_repo.execute_query(sql)
        except Exception:
            return []

        out: List[Dict[str, Any]] = []
        for r in rows or []:
            item = dict(r)
            if "created_date" in item:
                item["created_date"] = _normalize_ts(item.get("created_date"))
            item["mrn"] = mrn
            out.append(item)
        return out

    def _fetch_labs(self, allowed_schema: Dict[str, Any], *, ap_patient_key: Optional[str]) -> List[Dict[str, Any]]:
        if not ap_patient_key:
            return []
        if "ap_diagnostic_order_tests_result" not in allowed_schema:
            return []
        if "ap_diagnostic_test" not in allowed_schema:
            return []

        r_cols = set((allowed_schema.get("ap_diagnostic_order_tests_result") or {}).get("columns", []))
        dt_cols = set((allowed_schema.get("ap_diagnostic_test") or {}).get("columns", []))

        select_pairs = []
        # result columns
        for c in [
            "created_at",
            "result_value_number",
            "result_text",
            "marker",
            "result_type",
            "normal_range_value",
            "status_lkey",
        ]:
            if c in r_cols:
                select_pairs.append((f"r.{c}", c))
        # diagnostic test name
        if "test_name" in dt_cols:
            select_pairs.append(("dt.test_name", "test_name"))

        if not select_pairs:
            return []

        safe_key = _escape_sql_literal(ap_patient_key)
        sql = (
            "SELECT "
            + ", ".join(f"{expr} AS {alias}" for expr, alias in select_pairs)
            + " FROM ap_diagnostic_order_tests_result r "
            "LEFT JOIN ap_diagnostic_test dt ON dt.key = r.medical_test_key AND dt.is_valid = 1 "
            f"WHERE r.patient_key = '{safe_key}' AND r.is_valid = 1 "
            "ORDER BY r.created_at DESC LIMIT 20"
        )
        try:
            rows = self.hospital_repo.execute_query(sql)
        except Exception:
            return []

        out: List[Dict[str, Any]] = []
        for r in rows or []:
            item = dict(r)
            if "created_at" in item:
                item["created_at"] = _normalize_ts(item.get("created_at"))
            out.append(item)
        return out

    def _fetch_medications(self, allowed_schema: Dict[str, Any], *, ap_patient_key: Optional[str]) -> List[Dict[str, Any]]:
        if not ap_patient_key:
            return []
        safe_key = _escape_sql_literal(ap_patient_key)

        meds: List[Dict[str, Any]] = []

        def fetch_from(table: str, *, join_generic_key: str) -> None:
            if table not in allowed_schema or "ap_generic_medication" not in allowed_schema:
                return
            m_cols = set((allowed_schema.get(table) or {}).get("columns", []))
            g_cols = set((allowed_schema.get("ap_generic_medication") or {}).get("columns", []))

            select_pairs = []
            for c in [
                "created_at",
                "status_lkey",
                "dose",
                "dose_unit_lkey",
                "frequency",
                "roa_lkey",
                "start_date_time",
                "duration",
                "duration_type_lkey",
                "notes",
                "prn_indication",
                "special_instructions",
            ]:
                if c in m_cols:
                    select_pairs.append((f"m.{c}", c))
            if "generic_name" in g_cols:
                select_pairs.append(("g.generic_name", "generic_name"))

            if not select_pairs:
                return

            sql = (
                "SELECT "
                + ", ".join(f"{expr} AS {alias}" for expr, alias in select_pairs)
                + f" FROM {table} m "
                f"LEFT JOIN ap_generic_medication g ON g.key = m.{join_generic_key} AND g.is_valid = 1 "
                f"WHERE m.patient_key = '{safe_key}' "
                "ORDER BY m.created_at DESC LIMIT 20"
            )
            try:
                rows = self.hospital_repo.execute_query(sql)
            except Exception:
                return

            for r in rows or []:
                item = dict(r)
                if "created_at" in item:
                    item["created_at"] = _normalize_ts(item.get("created_at"))
                if "start_date_time" in item:
                    item["start_date_time"] = _normalize_ts(item.get("start_date_time"))
                item["source"] = table
                meds.append(item)

        fetch_from("ap_drug_order_medications", join_generic_key="generic_medications_key")
        fetch_from("ap_prescription_medications", join_generic_key="generic_medications_id")

        return meds

    def _fetch_allergies(
        self,
        allowed_schema: Dict[str, Any],
        *,
        ap_patient_key: Optional[str],
        base_profile: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        if ap_patient_key and "ap_patient_allergies" in allowed_schema and "ap_allergens" in allowed_schema:
            safe_key = _escape_sql_literal(ap_patient_key)
            sql = (
                "SELECT a.allergen_name AS allergen_name, pa.severity_lkey AS severity, pa.reaction AS reaction, "
                "pa.notes AS notes, pa.date_diagnosed AS date_diagnosed "
                "FROM ap_patient_allergies pa "
                "LEFT JOIN ap_allergens a ON a.key = pa.allergy_key AND a.is_valid = 1 "
                f"WHERE pa.patient_key = '{safe_key}' AND pa.is_valid = 1 "
                "ORDER BY pa.created_at DESC LIMIT 50"
            )
            try:
                rows = self.hospital_repo.execute_query(sql)
                out: List[Dict[str, Any]] = []
                for r in rows or []:
                    item = dict(r)
                    if "date_diagnosed" in item:
                        item["date_diagnosed"] = _normalize_ts(item.get("date_diagnosed"))
                    out.append(item)
                return out
            except Exception:
                pass

        # Fallback: aggregated allergy string if present in the base profile
        agg = base_profile.get("patient_health_allergies")
        if agg:
            return [{"allergen_name": str(agg)}]
        return []

    def _fetch_visit_history(self, allowed_schema: Dict[str, Any], *, ap_patient_key: Optional[str]) -> List[Dict[str, Any]]:
        if not ap_patient_key or "ap_encounter" not in allowed_schema:
            return []
        cols = set((allowed_schema.get("ap_encounter") or {}).get("columns", []))
        select_cols = []
        for c in [
            "created_at",
            "actual_start_date",
            "discharge_at",
            "encounter_status_lkey",
            "encounter_type_lkey",
            "chief_complaint",
            "department_key",
            "facility_key",
            "visit_id",
        ]:
            if c in cols:
                select_cols.append(c)
        if not select_cols:
            return []
        safe_key = _escape_sql_literal(ap_patient_key)
        sql = (
            "SELECT "
            + ", ".join(f"e.{c} AS {c}" for c in select_cols)
            + " FROM ap_encounter e "
            f"WHERE e.patient_key = '{safe_key}' AND e.is_valid = 1 "
            "ORDER BY e.created_at DESC LIMIT 10"
        )
        try:
            rows = self.hospital_repo.execute_query(sql)
        except Exception:
            return []
        out: List[Dict[str, Any]] = []
        for r in rows or []:
            item = dict(r)
            for k in ("created_at", "actual_start_date", "discharge_at"):
                if k in item:
                    item[k] = _normalize_ts(item.get(k))
            out.append(item)
        return out

    def _fetch_diagnoses(self, allowed_schema: Dict[str, Any], *, ap_patient_key: Optional[str]) -> List[Dict[str, Any]]:
        if not ap_patient_key or "ap_patient_diagnose" not in allowed_schema:
            return []
        cols = set((allowed_schema.get("ap_patient_diagnose") or {}).get("columns", []))
        select_cols = []
        for c in [
            "diagnose_code",
            "description",
            "diagnose_type_lkey",
            "diagnose_status_lkey",
            "date_diagnosed",
            "onset_date",
            "is_major",
            "is_suspected",
            "created_at",
            "notes",
        ]:
            if c in cols:
                select_cols.append(c)
        if not select_cols:
            return []
        safe_key = _escape_sql_literal(ap_patient_key)
        sql = (
            "SELECT "
            + ", ".join(f"d.{c} AS {c}" for c in select_cols)
            + " FROM ap_patient_diagnose d "
            f"WHERE d.patient_key = '{safe_key}' AND d.is_valid = 1 "
            "ORDER BY d.created_at DESC LIMIT 20"
        )
        try:
            rows = self.hospital_repo.execute_query(sql)
        except Exception:
            return []

        out: List[Dict[str, Any]] = []
        for r in rows or []:
            item = dict(r)
            for k in ("created_at", "date_diagnosed", "onset_date"):
                if k in item:
                    item[k] = _normalize_ts(item.get(k))
            out.append(item)
        return out


# Convenience function matching the requested signature.
_patient_record_service = PatientRecordService()


def get_patient_record_by_mrn(mrn: str, *, user_id: str = "u101") -> Optional[PatientRecord]:
    return _patient_record_service.get_patient_record_by_mrn(user_id, mrn)

