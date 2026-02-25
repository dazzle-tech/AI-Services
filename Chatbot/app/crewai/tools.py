# medai_crewai_tools.py
import requests
from typing import Type
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
from app.core.config import settings

SQL_GEN_URL = settings.sql_gen_url
VALIDATOR_URL = settings.validator_url
FORMATTER_URL = settings.formatter_url

# ---------- Tool input schemas ----------

class SQLGenInput(BaseModel):
    text: str = Field(..., description="Natural language hospital query + context.")
    user_id: str = Field("default_user", description="Hospital user id, e.g. u101/u102/u100.")

class ValidatorInput(BaseModel):
    sql_query: str = Field(..., description="SQL query to validate and execute.")
    user_id: str = Field("default_user", description="Hospital user id, e.g. u101/u102/u100.")

class FormatterInput(BaseModel):
    user_intent: str = Field(..., description="Original doctor/nurse question.")
    rows: list[dict] = Field(default_factory=list, description="Rows returned from DB.")
    columns: list[str] | None = None

# ---------- Tools ----------

class SQLGenTool(BaseTool):
    name: str = "sql_generator"
    description: str = (
        "Generate a single SQLite SQL query for the hospital.db "
        "based on a natural language question. Use this first for data questions."
    )
    args_schema: Type[SQLGenInput] = SQLGenInput

    def _run(self, text: str, user_id: str = "default_user") -> str:
        resp = requests.post(
            f"{SQL_GEN_URL}/generate",
            json={"user_id": user_id, "text": text},
            timeout=60
        )
        resp.raise_for_status()
        data = resp.json()
        return data["sql_query"]  # your service returns sql_query


class ValidatorTool(BaseTool):
    name: str = "sql_validator"
    description: str = (
        "Validate and execute an SQL query against hospital.db "
        "with row-level access control."
    )
    args_schema: Type[ValidatorInput] = ValidatorInput

    def _run(self, sql_query: str, user_id: str = "default_user") -> dict:
        resp = requests.post(
            f"{VALIDATOR_URL}/validate",
            json={"user_id": user_id, "sql_query": sql_query},
            timeout=60
        )
        resp.raise_for_status()
        data = resp.json()
        result = data["validation_result"]
        return {
            "valid": result.get("valid"),
            "message": result.get("message"),
            "rows": result.get("rows", []),
            "row_count": result.get("row_count", 0),
        }


class FormatterTool(BaseTool):
    name: str = "result_formatter"
    description: str = (
        "Turn raw DB rows into a short, human summary + table JSON for the UI."
    )
    args_schema: Type[FormatterInput] = FormatterInput

    def _run(self, user_intent: str, rows: list[dict], columns: list[str] | None = None) -> dict:
        payload = {
            "user_intent": user_intent,
            "result_rows": rows,
            "column_meta": [{"name": c} for c in (columns or (rows[0].keys() if rows else []))],
            "role": "doctor",
        }
        resp = requests.post(f"{FORMATTER_URL}/format_results", json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()  # contains summary + json.table + json.columns
