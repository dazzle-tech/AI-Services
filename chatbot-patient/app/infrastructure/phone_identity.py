"""Resolve a WhatsApp phone number via the Asklepios ``patients`` table.

Registration rule: the phone must match a row in ``patients`` (primary_mobile_number,
second_mobile_number, home_phone, or work_phone). The patient's MRN
(``medical_record_number``, e.g. P100) is then used to load their record.

    SELECT id, medical_record_number, first_name, last_name, primary_mobile_number
    FROM patients
    WHERE … phone columns match '+972595788143' …
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

_E164_RE = re.compile(r"^\+[1-9]\d{6,14}$")
_PHONE_COL_RE = re.compile(r"(phone|mobile)", re.I)
_SKIP_PHONE_COLS = {"emergency_contact_phone"}

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    _PSYCOPG2 = True
except ImportError:
    psycopg2 = None
    RealDictCursor = None
    _PSYCOPG2 = False


@dataclass(frozen=True)
class ResolvedPatient:
    patient_id: int
    patient_name: Optional[str]
    phone_number: str
    medical_record_number: Optional[str] = None


def normalize_phone(phone_number: str) -> str:
    cleaned = re.sub(r"[^\d+]", "", phone_number or "")
    if not cleaned:
        raise ValueError(f"Invalid phone number: {phone_number!r}")
    if not cleaned.startswith("+"):
        cleaned = f"+{cleaned.lstrip('0')}"
    if not _E164_RE.match(cleaned):
        raise ValueError(f"Invalid E.164 phone number: {phone_number!r}")
    return cleaned


def _digits(phone: str) -> str:
    return re.sub(r"\D", "", phone or "")


def _phones_match(stored: str, incoming_digits: str) -> bool:
    a, b = _digits(stored), incoming_digits
    if not a or not b:
        return False
    if a == b:
        return True
    n = min(len(a), len(b), 10)
    return n >= 7 and (a.endswith(b[-n:]) or b.endswith(a[-n:]))


def _patient_phone_columns() -> List[str]:
    path = Path(settings.schema_graph_path)
    try:
        graph = json.loads(path.read_text(encoding="utf-8"))
        cols = list((graph.get("patients") or {}).get("columns") or [])
    except Exception as exc:
        logger.warning("Could not load schema graph from %s: %s", path, exc)
        cols = [
            "primary_mobile_number",
            "second_mobile_number",
            "home_phone",
            "work_phone",
        ]
    return [c for c in cols if _PHONE_COL_RE.search(c) and c not in _SKIP_PHONE_COLS]


def _pg_connect():
    if not _PSYCOPG2:
        raise ImportError("psycopg2-binary is required for PostgreSQL")
    return psycopg2.connect(
        host=settings.db_host,
        port=settings.db_port,
        database=settings.db_name,
        user=settings.db_user,
        password=settings.db_password,
        options=f"-c search_path={settings.db_schema}",
    )


def _name_from_row(row: Dict[str, Any]) -> Optional[str]:
    parts = [str(row.get(k) or "").strip() for k in ("first_name", "last_name")]
    name = " ".join(p for p in parts if p)
    return name or None


def lookup_patient_by_phone(phone: str) -> Optional[Dict[str, Any]]:
    """Find a patient row whose phone columns match ``phone`` (E.164)."""
    cols = _patient_phone_columns()
    if not cols:
        return None
    incoming = _digits(phone)
    needles = {incoming}
    if len(incoming) >= 9:
        needles.add(incoming[-9:])
    if len(incoming) >= 10:
        needles.add(incoming[-10:])

    select_cols = ", ".join(
        ["id", "medical_record_number", "first_name", "last_name"] + cols
    )
    clauses, params = [], []
    for col in cols:
        for needle in needles:
            clauses.append(
                f"regexp_replace(CAST({col} AS TEXT), '\\D', '', 'g') LIKE %s"
            )
            params.append(f"%{needle}")

    sql = f"SELECT {select_cols} FROM patients WHERE ({' OR '.join(clauses)}) LIMIT 20"
    conn = _pg_connect()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(sql, params)
        for row in cur.fetchall():
            d = dict(row)
            for col in cols:
                if _phones_match(str(d.get(col) or ""), incoming):
                    return d
        return None
    finally:
        conn.close()


def lookup_patient_by_mrn(mrn: str) -> Optional[Dict[str, Any]]:
    conn = _pg_connect()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            """
            SELECT id, medical_record_number, first_name, last_name,
                   primary_mobile_number, date_of_birth, sex_at_birth, email
            FROM patients
            WHERE medical_record_number = %s
            LIMIT 1
            """,
            (mrn,),
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def resolve_patient_from_phone(phone_number: str) -> Optional[ResolvedPatient]:
    try:
        normalized = normalize_phone(phone_number)
    except ValueError:
        logger.warning("Invalid WhatsApp phone for identity lookup: %s", phone_number)
        return None

    try:
        row = lookup_patient_by_phone(normalized)
    except Exception as exc:
        logger.warning("patients table lookup failed: %s", exc)
        return None

    if not row:
        logger.info("patients: no row matching phone %s", normalized)
        return None

    pid = int(row["id"])
    mrn = str(row.get("medical_record_number") or "")
    logger.info(
        "patients: phone=%s matched id=%s mrn=%s",
        normalized, pid, mrn or "(none)",
    )
    return ResolvedPatient(
        patient_id=pid,
        patient_name=_name_from_row(row),
        phone_number=normalized,
        medical_record_number=mrn or None,
    )
