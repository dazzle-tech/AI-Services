"""Read patient record data from the Asklepios PostgreSQL ``patients`` table and related tables.

Used when ``DB_TYPE=postgresql`` so WhatsApp / web sessions keyed by MRN (e.g. P100)
do not call the demo SQLite MyRecordService (which only knows local demo ids).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.infrastructure.phone_identity import _pg_connect

logger = logging.getLogger(__name__)

DISCLAIMER = (
    "This is a copy of information already in your hospital record. It is not medical "
    "advice and has not been interpreted for you. Please talk to your care team about "
    "what any result means."
)


def _table_exists(cur, name: str) -> bool:
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = current_schema() AND table_name = %s
        )
        """,
        (name,),
    )
    return bool(cur.fetchone()[0])


def _patient_row(cur, *, patient_id: Optional[int], mrn: Optional[str]) -> Optional[Dict[str, Any]]:
    if patient_id is not None:
        cur.execute(
            """
            SELECT id, medical_record_number, first_name, second_name, last_name,
                   date_of_birth, sex_at_birth, primary_mobile_number, second_mobile_number,
                   home_phone, work_phone, email, emergency_contact_name, emergency_contact_phone
            FROM patients WHERE id = %s LIMIT 1
            """,
            (patient_id,),
        )
    elif mrn:
        cur.execute(
            """
            SELECT id, medical_record_number, first_name, second_name, last_name,
                   date_of_birth, sex_at_birth, primary_mobile_number, second_mobile_number,
                   home_phone, work_phone, email, emergency_contact_name, emergency_contact_phone
            FROM patients WHERE medical_record_number = %s LIMIT 1
            """,
            (mrn,),
        )
    else:
        return None
    row = cur.fetchone()
    if not row:
        return None
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, row))


def _name(row: Dict[str, Any]) -> str:
    parts = [str(row.get(k) or "").strip() for k in ("first_name", "last_name")]
    return " ".join(p for p in parts if p) or "Patient"


def fetch_my_record(
    *,
    patient_id: Optional[int] = None,
    patient_mrn: Optional[str] = None,
    sections: Optional[List[str]] = None,
    lab_limit: int = 12,
) -> Dict[str, Any]:
    conn = _pg_connect()
    try:
        cur = conn.cursor()
        row = _patient_row(cur, patient_id=patient_id, mrn=patient_mrn)
        if not row:
            raise ValueError(f"No patient found for mrn={patient_mrn!r} id={patient_id}")

        pid = int(row["id"])
        mrn = str(row.get("medical_record_number") or patient_mrn or "")
        wanted = sections or ["all"]
        if "all" in [s.lower() for s in wanted]:
            wanted = ["profile", "allergies", "conditions", "medications", "labs", "visits", "vitals"]

        out: Dict[str, Any] = {
            "patient_id": pid,
            "medical_record_number": mrn,
            "sections_returned": wanted,
            "disclaimer": DISCLAIMER,
            "has_critical_result": False,
        }

        if "profile" in wanted:
            out["profile"] = {
                "patient_id": pid,
                "medical_record_number": mrn,
                "name": _name(row),
                "date_of_birth": str(row.get("date_of_birth") or "")[:10] or None,
                "gender": row.get("sex_at_birth"),
                "phone": row.get("primary_mobile_number") or row.get("home_phone"),
                "email": row.get("email"),
                "emergency_contact": row.get("emergency_contact_name"),
                "emergency_contact_phone": row.get("emergency_contact_phone"),
            }

        if "allergies" in wanted and _table_exists(cur, "patient_allergies"):
            cur.execute(
                """
                SELECT pa.allergen_type, pa.severity, pa.note, a.name AS allergen_name
                FROM patient_allergies pa
                LEFT JOIN allergens a ON a.id = pa.allergen_id
                WHERE pa.patient_id = %s
                ORDER BY pa.created_date DESC NULLS LAST
                LIMIT 20
                """,
                (pid,),
            )
            allergies = []
            for r in cur.fetchall():
                label = r[3] or r[0] or "Allergy"
                if r[1]:
                    label = f"{label} ({r[1]})"
                allergies.append(label)
            out["allergies"] = allergies

        if "conditions" in wanted and _table_exists(cur, "patient_diagnoses"):
            try:
                cur.execute(
                    """
                    SELECT ic.icd_short_description, ic.icd_code, pd.type, pd.created_date
                    FROM patient_diagnoses pd
                    LEFT JOIN icd_diagnosis ic ON ic.id = pd.diagnosis_id
                    WHERE pd.patient_id = %s
                    ORDER BY pd.created_date DESC NULLS LAST
                    LIMIT 20
                    """,
                    (pid,),
                )
                out["conditions"] = [
                    {
                        "name": r[0] or "Condition",
                        "code": r[1],
                        "type": r[2],
                        "diagnosed_on": str(r[3])[:10] if r[3] else None,
                    }
                    for r in cur.fetchall()
                ]
            except Exception as exc:
                logger.warning("conditions lookup failed for patient %s: %s", pid, exc)
                out["conditions"] = []

        if "labs" in wanted and _table_exists(cur, "diagnostic_order_tests_result"):
            cur.execute(
                """
                SELECT dt.name, dotr.result_value_text, dotr.result_value_number,
                       dotr.normal_range_value, dotr.marker, dot.approved_date
                FROM diagnostic_order_tests_result dotr
                JOIN diagnostic_order_tests dot ON dotr.order_test_id = dot.id
                JOIN diagnostic_orders d ON dot.order_id = d.id
                LEFT JOIN diagnostic_test dt ON dt.id = dot.test_id
                WHERE d.patient_id = %s
                ORDER BY dot.approved_date DESC NULLS LAST
                LIMIT %s
                """,
                (pid, lab_limit),
            )
            labs = []
            for r in cur.fetchall():
                value = r[1] if r[1] not in (None, "") else r[2]
                flag = (r[4] or "").lower() if r[4] else None
                if flag == "critical":
                    out["has_critical_result"] = True
                labs.append({
                    "name": r[0] or "Lab test",
                    "value": str(value) if value is not None else None,
                    "reference_range": r[3],
                    "flag": flag,
                    "taken_at": str(r[5])[:16] if r[5] else None,
                })
            out["labs"] = labs

        if "vitals" in wanted and _table_exists(cur, "vital_signs"):
            cur.execute(
                """
                SELECT created_date, heart_rate, blood_pressure_systolic,
                       blood_pressure_diastolic, temperature, oxygen_saturation, respiratory_rate
                FROM vital_signs
                WHERE patient_id = %s AND (is_active IS NULL OR is_active = TRUE)
                ORDER BY created_date DESC NULLS LAST
                LIMIT 8
                """,
                (pid,),
            )
            vitals = []
            for r in cur.fetchall():
                bp = None
                if r[2] is not None and r[3] is not None:
                    bp = f"{r[2]}/{r[3]}"
                vitals.append({
                    "taken_at": str(r[0])[:16] if r[0] else None,
                    "heart_rate": r[1],
                    "blood_pressure": bp,
                    "temperature_c": float(r[4]) if r[4] is not None else None,
                    "oxygen_saturation": r[5],
                    "respiratory_rate": r[6],
                })
            out["vitals"] = vitals

        if "visits" in wanted and _table_exists(cur, "appointment"):
            cur.execute(
                """
                SELECT id, start_datetime, end_datetime, status, reason
                FROM appointment
                WHERE patient_id = %s
                ORDER BY start_datetime DESC NULLS LAST
                LIMIT 10
                """,
                (pid,),
            )
            out["visits"] = [
                {
                    "admission_id": r[0],
                    "admitted_on": str(r[1])[:16] if r[1] else None,
                    "discharged_on": str(r[2])[:16] if r[2] else None,
                    "status": r[3],
                    "reason": r[4],
                }
                for r in cur.fetchall()
            ]

        if "medications" in wanted:
            out["medications"] = []

        return out
    finally:
        conn.close()


def fetch_appointments_list(*, patient_id: int, include_past: bool = False) -> Dict[str, Any]:
    conn = _pg_connect()
    try:
        cur = conn.cursor()
        if not _table_exists(cur, "appointment"):
            return {"upcoming": [], "past": []}
        clause = "" if include_past else "AND start_datetime >= NOW()"
        cur.execute(
            f"""
            SELECT id, start_datetime, end_datetime, status, reason, default_practitioner_id
            FROM appointment
            WHERE patient_id = %s {clause}
            ORDER BY start_datetime ASC
            LIMIT 20
            """,
            (patient_id,),
        )
        upcoming = []
        for r in cur.fetchall():
            start = r[1]
            upcoming.append({
                "appt_id": r[0],
                "date": str(start.date()) if start else None,
                "time": str(start.strftime("%H:%M")) if start else None,
                "status": r[3],
                "reason": r[4],
                "provider_id": r[5],
                "provider": r[5] or "Hospital",
            })
        return {"upcoming": upcoming, "past": []}
    finally:
        conn.close()
