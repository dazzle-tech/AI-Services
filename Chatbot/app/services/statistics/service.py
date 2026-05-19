"""Statistics service layer: parse -> build SQL -> validate -> execute -> format."""

from __future__ import annotations

import logging
import pprint
from datetime import date
from typing import Any, Dict, Optional

from app.infrastructure.db.hospital_repo import HospitalRepository

from .parser import parse_statistics_request
from .query_builder import (
    StatisticsQueryMeta,
    StatisticsSQLValidationError,
    build_statistics_sql,
)
from .formatter import format_statistics_response

logger = logging.getLogger(__name__)


def _preview_rows(rows: Any, *, max_rows: int = 10, max_chars: int = 2000) -> str:
    try:
        if isinstance(rows, list):
            snippet = rows[:max_rows]
            text = pprint.pformat(snippet, width=120, compact=True)
            if len(rows) > max_rows:
                text = f"{text} ... (+{len(rows) - max_rows} more)"
        else:
            text = pprint.pformat(rows, width=120, compact=True)
        if len(text) > max_chars:
            return text[:max_chars] + "…"
        return text
    except Exception as e:  # pragma: no cover
        return f"<unprintable rows: {e}>"


def _preview_sql(sql: str, *, max_chars: int = 8000) -> str:
    s = (sql or "").strip()
    if len(s) <= max_chars:
        return s
    return s[:max_chars] + "…"


class StatisticsService:
    """Dedicated pipeline for aggregate-only statistics queries."""

    def __init__(self, hospital_repo: Optional[HospitalRepository] = None):
        self.hospital_repo = hospital_repo or HospitalRepository()

    def handle(
        self,
        message: str,
        *,
        reference_date: Optional[date] = None,
        include_sql: bool = False,
    ) -> Dict[str, Any]:
        try:
            parsed = parse_statistics_request(message, reference_date=reference_date)
            sql, meta = build_statistics_sql(
                parsed, db_type=getattr(self.hospital_repo, "db_type", "sqlite")
            )
            logger.info(
                "📊 [STATISTICS] Generated aggregate SQL: %s",
                _preview_sql(sql),
            )
            try:
                rows = self.hospital_repo.execute_query(sql)
            except Exception as e:
                logger.error("❌ [STATISTICS] Query execution failed: %s", e, exc_info=True)
                return self._structured_error(
                    "Statistics query failed to execute. Please try a different time range or metric.",
                    error_detail=str(e),
                    include_sql=include_sql,
                    sql=sql,
                )
            safe_rows = rows or []
            logger.info(
                "📊 [STATISTICS] Query returned %d row(s). Rows preview: %s",
                len(safe_rows) if isinstance(safe_rows, list) else 0,
                _preview_rows(safe_rows),
            )
            result_json = format_statistics_response(parsed=parsed, rows=safe_rows, meta=meta)
            result: Dict[str, Any] = {
                "intent": "statistics",
                "mode": "statistics",
                "text": result_json.get("summary") or "",
                "data_json": result_json,
            }
            if include_sql:
                result["meta"] = {"sql": sql}
            return result
        except (ValueError, StatisticsSQLValidationError) as e:
            return self._structured_error(
                str(e),
                error_detail=str(e),
                include_sql=include_sql,
                sql=None,
            )

    def _structured_error(
        self,
        user_message: str,
        *,
        error_detail: str,
        include_sql: bool,
        sql: Optional[str],
    ) -> Dict[str, Any]:
        parsed_fallback = {
            "intent": "statistics_error",
            "metric": "count",
            "entity": "unknown",
            "group_by": None,
            "top_n": None,
            "time_range": {"type": None},
        }
        result_json = {
            "mode": "statistics",
            "title": "Statistics query needs clarification",
            "summary": user_message,
            "visualization": {"type": "kpi"},
            "table": {"columns": ["Message", "Value"], "rows": [["Error", user_message]]},
            "chart_data": {"x": ["Error"], "y": [1]},
            "filters": {"date_range": None},
            "parsed": parsed_fallback,
        }
        result: Dict[str, Any] = {
            "intent": "statistics",
            "mode": "statistics",
            "text": user_message,
            "data_json": result_json,
            "meta": {"error": error_detail},
        }
        if include_sql and sql:
            result["meta"]["sql"] = sql
        return result
