"""Format statistics query results for UI consumption."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, List, Tuple

from .query_builder import StatisticsQueryMeta


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _build_table(meta: StatisticsQueryMeta, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    col1, col2 = meta.table_columns
    out_rows: List[List[Any]] = []

    if meta.visualization_type == "kpi":
        count_val = None
        if rows and isinstance(rows[0], dict):
            count_val = rows[0].get("count")
        out_rows = [[meta.title, count_val if count_val is not None else 0]]
        return {"columns": [col1, col2], "rows": out_rows}

    # Default: use first 2 columns heuristically.
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        if "diagnosis" in r and "count" in r:
            out_rows.append([r.get("diagnosis"), r.get("count")])
        elif "department" in r and "count" in r:
            out_rows.append([r.get("department"), r.get("count")])
        elif "month" in r and "count" in r:
            out_rows.append([r.get("month"), r.get("count")])
        else:
            keys = list(r.keys())
            if len(keys) >= 2:
                out_rows.append([r.get(keys[0]), r.get(keys[1])])

    return {"columns": [col1, col2], "rows": out_rows}


def _build_chart_data(meta: StatisticsQueryMeta, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    x: List[Any] = []
    y: List[Any] = []

    if meta.visualization_type == "kpi":
        val = 0
        if rows and isinstance(rows[0], dict):
            raw = rows[0].get("count")
            try:
                val = int(raw)
            except Exception:
                try:
                    val = float(raw)
                except Exception:
                    val = 0
        return {"x": [meta.title], "y": [val]}

    for r in rows or []:
        if not isinstance(r, dict):
            continue
        if "diagnosis" in r and "count" in r:
            x.append(r.get("diagnosis"))
            y.append(r.get("count"))
        elif "department" in r and "count" in r:
            x.append(r.get("department"))
            y.append(r.get("count"))
        elif "month" in r and "count" in r:
            x.append(r.get("month"))
            y.append(r.get("count"))

    return {"x": x, "y": y}


def _summary_from_rows(meta: StatisticsQueryMeta, rows: List[Dict[str, Any]]) -> str:
    if meta.visualization_type == "kpi":
        val = 0
        if rows and isinstance(rows[0], dict):
            val = rows[0].get("count") or 0
        return f"{meta.title}: {val}."

    if not rows:
        return f"{meta.title}: no data found for the selected time range."

    first = rows[0] if isinstance(rows[0], dict) else {}
    if "diagnosis" in first and "count" in first:
        diag = first.get("diagnosis")
        cnt = first.get("count")
        return f"{diag} was the most common diagnosis with {cnt} cases."
    if "department" in first and "count" in first:
        dep = first.get("department")
        cnt = first.get("count")
        return f"{dep} was the busiest department with {cnt} admissions."
    if "month" in first and "count" in first:
        return f"{meta.title}: {len(rows)} month bucket(s) returned."
    return f"{meta.title}: {len(rows)} row(s) returned."


def format_statistics_response(
    *,
    parsed: Dict[str, Any],
    rows: List[Dict[str, Any]],
    meta: StatisticsQueryMeta,
) -> Dict[str, Any]:
    tr = parsed.get("time_range") or {}
    title = meta.title

    visualization = {"type": meta.visualization_type}
    table = _build_table(meta, rows)
    chart_data = _build_chart_data(meta, rows)
    summary = _summary_from_rows(meta, rows)

    return {
        "mode": "statistics",
        "title": title,
        "summary": summary,
        "visualization": visualization,
        "table": table,
        "chart_data": chart_data,
        "filters": {"date_range": tr.get("type")},
        "parsed": parsed,
    }

