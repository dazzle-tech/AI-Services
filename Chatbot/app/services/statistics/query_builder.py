"""Aggregate-only SQL builder and validator for statistics queries."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, Optional, Tuple


class StatisticsSQLValidationError(ValueError):
    pass


def _escape_sql_literal(value: str) -> str:
    return (value or "").replace("'", "''")


@dataclass(frozen=True)
class StatisticsQueryMeta:
    title: str
    visualization_type: str
    table_columns: Tuple[str, str]
    x_label: str
    y_label: str


_FORBIDDEN_SQL_RE = re.compile(
    r"\b("
    r"insert|update|delete|drop|alter|truncate|create|attach|detach|pragma|vacuum|reindex|"
    r"copy|grant|revoke"
    r")\b",
    re.IGNORECASE,
)

_FORBIDDEN_FIELDS_RE = re.compile(
    r"\b("
    r"mrn|medical_record_number|patient_full_name|patient_name|dob|date_of_birth|"
    r"patient_key|patient_id|patients_id|ssn|address|phone|email"
    r")\b",
    re.IGNORECASE,
)

_FORBIDDEN_STAR_RE = re.compile(r"select\s+\*|select\s+[^;]*\.\*", re.IGNORECASE | re.DOTALL)


def validate_statistics_sql(sql: str) -> None:
    if not sql or not sql.strip():
        raise StatisticsSQLValidationError("Empty SQL")
    sql_s = sql.strip()
    if not sql_s.lower().startswith("select"):
        raise StatisticsSQLValidationError("Statistics SQL must be SELECT-only")
    if _FORBIDDEN_SQL_RE.search(sql_s):
        raise StatisticsSQLValidationError("Forbidden SQL operation detected")
    if _FORBIDDEN_STAR_RE.search(sql_s):
        raise StatisticsSQLValidationError("SELECT * is not allowed in statistics mode")
    if _FORBIDDEN_FIELDS_RE.search(sql_s):
        raise StatisticsSQLValidationError("Patient-level/identifier fields are not allowed in statistics mode")
    # Disallow joining patient tables entirely in this mode.
    if re.search(r"\bjoin\s+patients\b|\bfrom\s+patients\b", sql_s, flags=re.IGNORECASE):
        raise StatisticsSQLValidationError("Joining patient-level tables is not allowed in statistics mode")
    if re.search(r"\bjoin\s+ap_patient\b|\bfrom\s+ap_patient\b", sql_s, flags=re.IGNORECASE):
        raise StatisticsSQLValidationError("Joining patient-level tables is not allowed in statistics mode")
    if not sql_s.endswith(";"):
        raise StatisticsSQLValidationError("SQL must end with ';'")


def _parse_date(s: str) -> date:
    try:
        return date.fromisoformat(s)
    except Exception as e:
        raise StatisticsSQLValidationError(f"Invalid date: {s}") from e


def _date_bucket_expr(db_type: str, column_expr: str) -> str:
    if (db_type or "").lower() == "postgresql":
        return f"DATE_TRUNC('month', {column_expr})::date"
    # SQLite
    return f"strftime('%Y-%m-01', {column_expr})"


def _created_at_to_date_expr(db_type: str, created_at_expr: str) -> str:
    """
    Convert numeric created_at (epoch milliseconds) into a date, per DB.

    Verified in local PostgreSQL: ap_* .created_at columns are NUMERIC millisecond epoch.
    """
    if (db_type or "").lower() == "postgresql":
        return f"to_timestamp({created_at_expr} / 1000.0)::date"

    # SQLite: support both numeric epoch-ms and ISO-like strings.
    # - If numeric: DATE(ms/1000, 'unixepoch')
    # - Else: DATE(text)
    return (
        "CASE "
        f"WHEN typeof({created_at_expr}) IN ('integer','real') THEN DATE({created_at_expr} / 1000, 'unixepoch') "
        f"ELSE DATE({created_at_expr}) "
        "END"
    )


def _coalesce_event_date_expr(db_type: str, primary_date_expr: str, created_at_expr: str) -> str:
    created_date = _created_at_to_date_expr(db_type, created_at_expr)
    if (db_type or "").lower() == "postgresql":
        return f"COALESCE({primary_date_expr}, {created_date})"
    # SQLite: normalize primary to DATE() string for consistent comparisons
    return f"COALESCE(DATE({primary_date_expr}), {created_date})"


def _timestamp_to_date_expr(db_type: str, ts_expr: str) -> str:
    """
    Convert a timestamp/date expression into a date for comparisons, per DB.
    """
    if (db_type or "").lower() == "postgresql":
        return f"({ts_expr})::date"
    return f"DATE({ts_expr})"


def _date_literal(db_type: str, iso_date: str) -> str:
    if (db_type or "").lower() == "postgresql":
        return f"DATE '{_escape_sql_literal(iso_date)}'"
    return f"'{_escape_sql_literal(iso_date)}'"


def build_statistics_sql(parsed: Dict[str, Any], *, db_type: str = "sqlite") -> Tuple[str, StatisticsQueryMeta]:
    """
    Build a strict, aggregate-only SQL query from a parsed request.

    This builder does not accept arbitrary user SQL and only emits safe templates.
    """
    intent = (parsed.get("intent") or "").strip().lower()
    entity = (parsed.get("entity") or "").strip().lower()
    metric = (parsed.get("metric") or "").strip().lower() or "count"
    group_by = parsed.get("group_by")
    top_n = parsed.get("top_n")

    tr = parsed.get("time_range") or {}
    start_s = str(tr.get("start_date") or "").strip()
    end_s = str(tr.get("end_date_exclusive") or "").strip()
    range_type = str(tr.get("type") or "").strip() or "custom"

    def human_range(rt: str) -> str:
        rt = (rt or "").strip().lower()
        if not rt:
            return "Custom Range"
        if rt.startswith("last_") and rt.endswith("_months"):
            n = rt.replace("last_", "").replace("_months", "")
            if n.isdigit():
                return f"Last {int(n)} Months"
        mapping = {
            "today": "Today",
            "this_week": "This Week",
            "last_week": "Last Week",
            "this_month": "This Month",
            "last_month": "Last Month",
            "this_year": "This Year",
        }
        return mapping.get(rt, rt.replace("_", " ").title())

    start = _parse_date(start_s)
    end = _parse_date(end_s)
    if end <= start:
        raise StatisticsSQLValidationError("Invalid time range (end <= start)")

    start_lit = start.isoformat()
    end_lit = end.isoformat()

    limit_clause = ""
    if isinstance(top_n, int) and 1 <= top_n <= 100:
        limit_clause = f" LIMIT {int(top_n)}"

    # Only COUNT/SUM/AVG are allowed metrics.
    if metric not in {"count", "sum", "avg"}:
        raise StatisticsSQLValidationError(f"Unsupported metric: {metric}")

    # Entity → base table mapping (aggregate-friendly).
    if entity == "diagnosis":
        # Prefer the normalized schema for diagnoses.
        # - patient_diagnoses: diagnosis_id + created_date
        # - icd_diagnosis: descriptions for diagnosis_id
        event_date = (
            f"COALESCE({_timestamp_to_date_expr(db_type, 'pd.created_date')}, "
            f"{_timestamp_to_date_expr(db_type, 'pd.last_modified_date')})"
        )
        where = "WHERE 1=1"
        # NOTE: Some deployments have NULL created/modified timestamps in `patient_diagnoses`.
        # For all-time queries, skipping the date predicate avoids returning 0 rows.
        if range_type != "all_time":
            where = (
                f"{where} "
                f"AND {event_date} >= {_date_literal(db_type, start_lit)} "
                f"AND {event_date} < {_date_literal(db_type, end_lit)}"
            )
        if intent == "top_diagnoses" or (group_by == "diagnosis"):
            dx_desc = (
                "COALESCE("
                "NULLIF(TRIM(dx.icd_full_description), ''), "
                "NULLIF(TRIM(dx.icd_short_description), ''), "
                "NULLIF(TRIM(dx.icd_code), '')"
                ")"
            )
            dx_label = (
                "CASE "
                f"WHEN {dx_desc} IS NOT NULL THEN {dx_desc} "
                "WHEN pd.diagnosis_id IS NOT NULL THEN ('Unknown diagnosis (id: ' || CAST(pd.diagnosis_id AS TEXT) || ')') "
                "ELSE 'Unknown' "
                "END"
            )
            sql = (
                "SELECT "
                f"{dx_label} AS diagnosis, "
                "COUNT(*) AS count "
                "FROM patient_diagnoses pd "
                "LEFT JOIN icd_diagnosis dx ON dx.id = pd.diagnosis_id "
                f"{where} "
                "GROUP BY diagnosis "
                "ORDER BY count DESC"
                f"{limit_clause};"
            )
            meta = StatisticsQueryMeta(
                title=f"Top {int(top_n) if isinstance(top_n, int) else 5} Diagnoses {human_range(range_type)}",
                visualization_type="bar_chart",
                table_columns=("Diagnosis", "Count"),
                x_label="Diagnosis",
                y_label="Count",
            )
            validate_statistics_sql(sql)
            return sql, meta

        if intent == "diagnosis_trend" or (group_by == "month"):
            bucket = _date_bucket_expr(db_type, event_date)
            sql = (
                "SELECT "
                f"{bucket} AS month, "
                "COUNT(*) AS count "
                "FROM patient_diagnoses pd "
                "LEFT JOIN icd_diagnosis dx ON dx.id = pd.diagnosis_id "
                f"{where} "
                "GROUP BY month "
                "ORDER BY month ASC;"
            )
            meta = StatisticsQueryMeta(
                title=f"Diagnosis Trend {human_range(range_type)}",
                visualization_type="line_chart",
                table_columns=("Month", "Count"),
                x_label="Month",
                y_label="Count",
            )
            validate_statistics_sql(sql)
            return sql, meta

        # Fallback: KPI count of diagnosis records in range.
        sql = (
            "SELECT COUNT(*) AS count "
            "FROM patient_diagnoses pd "
            "LEFT JOIN icd_diagnosis dx ON dx.id = pd.diagnosis_id "
            f"{where};"
        )
        meta = StatisticsQueryMeta(
            title=f"Diagnoses {human_range(range_type)}",
            visualization_type="kpi",
            table_columns=("Metric", "Value"),
            x_label="Metric",
            y_label="Value",
        )
        validate_statistics_sql(sql)
        return sql, meta

    if entity == "admissions":
        event_date = _coalesce_event_date_expr(db_type, "e.actual_start_date", "e.created_at")
        where = (
            "WHERE e.is_valid = 1 "
            f"AND {event_date} >= {_date_literal(db_type, start_lit)} "
            f"AND {event_date} < {_date_literal(db_type, end_lit)}"
        )
        if intent == "admissions_count" or not group_by:
            sql = (
                "SELECT COUNT(*) AS count "
                "FROM ap_encounter e "
                f"{where};"
            )
            meta = StatisticsQueryMeta(
                title=f"Admissions {human_range(range_type)}",
                visualization_type="kpi",
                table_columns=("Metric", "Value"),
                x_label="Metric",
                y_label="Value",
            )
            validate_statistics_sql(sql)
            return sql, meta

        bucket = _date_bucket_expr(db_type, event_date)
        sql = (
            "SELECT "
            f"{bucket} AS month, "
            "COUNT(*) AS count "
            "FROM ap_encounter e "
            f"{where} "
            "GROUP BY month "
            "ORDER BY month ASC;"
        )
        meta = StatisticsQueryMeta(
            title=f"Admissions Trend {human_range(range_type)}",
            visualization_type="line_chart",
            table_columns=("Month", "Count"),
            x_label="Month",
            y_label="Count",
        )
        validate_statistics_sql(sql)
        return sql, meta

    if entity == "departments":
        # Prefer the normalized schema for encounters/departments.
        # - patient_encounters.department_id -> department.id
        # - patient_encounters.encounter_date/created_date timestamps
        event_date = (
            f"COALESCE("
            f"{_timestamp_to_date_expr(db_type, 'pe.encounter_date')}, "
            f"{_timestamp_to_date_expr(db_type, 'pe.created_date')}, "
            f"{_timestamp_to_date_expr(db_type, 'pe.last_modified_date')}"
            f")"
        )
        where = "WHERE 1=1"
        # Skip date predicate for all_time to avoid NULL-date rows being filtered out.
        if range_type != "all_time":
            where = (
                f"{where} "
                f"AND {event_date} >= {_date_literal(db_type, start_lit)} "
                f"AND {event_date} < {_date_literal(db_type, end_lit)}"
            )

        # Always aggregate by department for this entity.
        sql = (
            "SELECT "
            "COALESCE(NULLIF(TRIM(dep.name), ''), 'Unknown') AS department, "
            "COUNT(*) AS count "
            "FROM patient_encounters pe "
            "LEFT JOIN department dep ON dep.id = pe.department_id "
            f"{where} "
            "GROUP BY department "
            "ORDER BY count DESC"
            f"{limit_clause};"
        )
        meta = StatisticsQueryMeta(
            title=f"Busiest Departments {human_range(range_type)}",
            visualization_type="bar_chart",
            table_columns=("Department", "Count"),
            x_label="Department",
            y_label="Count",
        )
        validate_statistics_sql(sql)
        return sql, meta

    raise StatisticsSQLValidationError(f"Unsupported entity: {entity}")
