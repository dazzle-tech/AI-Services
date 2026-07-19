# medai_crewai_tools.py
import hashlib
import json
import logging
import requests
from typing import Type, Optional, List, Any
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
from app.core.config import settings
from app.infrastructure.db.audit_repo import AuditRepository
from app.services.confirmation_service import get_confirmation_service
from app.services.emr_service import submit_prescription

logger = logging.getLogger(__name__)


class ConfirmationRequired(Exception):
    """Raised when a protected action requires explicit confirmation."""


class MedAITool(BaseTool):
    """Base class for MedAI tools with execution audit metadata."""

    is_write_action: bool = False
    tool_category: str = "read"

    def _audit_execution(
        self,
        interaction_id: Optional[int],
        tool_name: str,
        user_id: str,
        role: str,
        is_write_action: bool,
        arguments_json: Any,
        result_json: Any,
        error: Optional[str],
        confirmation_token_id: Optional[str] = None,
        ok: bool = True,
    ) -> None:
        try:
            AuditRepository().insert_tool_execution(
                interaction_id=interaction_id,
                tool_name=tool_name,
                user_id=user_id,
                role=role,
                is_write_action=is_write_action,
                arguments_json=arguments_json,
                result_json=result_json,
                error=error,
                confirmation_token_id=confirmation_token_id,
                ok=ok,
            )
        except Exception as exc:
            logger.warning("Failed to audit tool execution: %s", exc)


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
    role: str = Field("doctor", description="Role of the requesting user.")

class PrescriptionDraftInput(BaseModel):
    user_id: str = Field("default_user", description="Hospital user id.")
    role: str = Field("doctor", description="User role.")
    patient_mrn: Optional[str] = Field(None, description="Patient medical record number.")
    medications: Optional[List[str]] = Field(None, description="List of medications to prescribe.")
    instructions: Optional[str] = Field(None, description="Clinical instructions for the prescription.")
    user_intent: Optional[str] = Field(None, description="Original user request text.")

class PrescriptionSubmitInput(BaseModel):
    user_id: str = Field("default_user", description="Hospital user id.")
    role: str = Field("doctor", description="User role.")
    patient_mrn: Optional[str] = Field(None, description="Patient medical record number.")
    draft_text: str = Field(..., description="Draft prescription text to submit.")
    confirmation_token: Optional[str] = Field(None, description="Confirmation token for protected submission.")
    note: Optional[str] = Field(None, description="Optional note or context for submission.")

# ---------- Tools ----------

class SQLGenTool(MedAITool):
    name: str = "sql_generator"
    description: str = (
        "Generate a hospital SQL query for the database based on a natural language question. "
        "Use this first for data requests."
    )
    args_schema: Type[SQLGenInput] = SQLGenInput
    tool_category: str = "read"
    is_write_action: bool = False

    def _run(self, text: str, user_id: str = "default_user", interaction_id: Optional[int] = None) -> str:
        result_json = None
        error = None
        try:
            resp = requests.post(
                f"{SQL_GEN_URL}/generate",
                json={"user_id": user_id, "text": text},
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            result_json = data
            return data.get("sql_query") or data.get("sql") or ""
        except Exception as exc:
            error = str(exc)
            raise
        finally:
            self._audit_execution(
                interaction_id=interaction_id,
                tool_name=self.name,
                user_id=user_id,
                role="",
                is_write_action=self.is_write_action,
                arguments_json={"text": text},
                result_json=result_json,
                error=error,
            )


class ValidatorTool(MedAITool):
    name: str = "sql_validator"
    description: str = (
        "Validate and execute an SQL query against the hospital database with role-based access control."
    )
    args_schema: Type[ValidatorInput] = ValidatorInput
    tool_category: str = "read"
    is_write_action: bool = False

    def _run(self, sql_query: str, user_id: str = "default_user", interaction_id: Optional[int] = None) -> dict:
        result_json = None
        error = None
        try:
            resp = requests.post(
                f"{VALIDATOR_URL}/validate",
                json={"user_id": user_id, "sql_query": sql_query},
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            result_json = data
            result = data.get("validation_result", {})
            return {
                "valid": result.get("valid"),
                "message": result.get("message"),
                "rows": result.get("rows", []),
                "row_count": result.get("row_count", 0),
            }
        except Exception as exc:
            error = str(exc)
            raise
        finally:
            self._audit_execution(
                interaction_id=interaction_id,
                tool_name=self.name,
                user_id=user_id,
                role="",
                is_write_action=self.is_write_action,
                arguments_json={"sql_query": sql_query},
                result_json=result_json,
                error=error,
            )


class FormatterTool(MedAITool):
    name: str = "result_formatter"
    description: str = (
        "Turn raw query results into a concise, human-readable summary with table metadata."
    )
    args_schema: Type[FormatterInput] = FormatterInput
    tool_category: str = "read"
    is_write_action: bool = False

    def _run(self, user_intent: str, rows: list[dict], columns: list[str] | None = None, role: str = "doctor", interaction_id: Optional[int] = None) -> dict:
        payload = {
            "user_intent": user_intent,
            "result_rows": rows,
            "column_meta": [{"name": c} for c in (columns or (rows[0].keys() if rows else []))],
            "role": role,
        }
        result_json = None
        error = None
        try:
            resp = requests.post(f"{FORMATTER_URL}/format_results", json=payload, timeout=60)
            resp.raise_for_status()
            result_json = resp.json()
            return result_json
        except Exception as exc:
            error = str(exc)
            raise
        finally:
            self._audit_execution(
                interaction_id=interaction_id,
                tool_name=self.name,
                user_id="",
                role=role,
                is_write_action=self.is_write_action,
                arguments_json={"user_intent": user_intent, "columns": columns, "role": role},
                result_json=result_json,
                error=error,
            )


class DraftPrescriptionTool(MedAITool):
    name: str = "draft_prescription"
    description: str = (
        "Create a draft prescription for a patient based on the request details. "
        "This is a staging step and does not submit anything to the EMR."
    )
    args_schema: Type[PrescriptionDraftInput] = PrescriptionDraftInput
    tool_category: str = "action"
    is_write_action: bool = False

    def _run(
        self,
        user_id: str,
        role: str,
        patient_mrn: Optional[str] = None,
        medications: Optional[List[str]] = None,
        instructions: Optional[str] = None,
        user_intent: Optional[str] = None,
        interaction_id: Optional[int] = None,
    ) -> dict:
        result_json = None
        error = None
        try:
            if role not in {"doctor", "nurse"}:
                return {
                    "ok": False,
                    "message": "Prescription drafting is only available to clinical staff with prescribing privileges.",
                }

            meds = medications or []
            meds_text = "; ".join([str(m).strip() for m in meds if m]) or "No medications specified."
            draft_body = (
                f"Prescription draft for patient MRN {patient_mrn or '[unknown MRN]'}:\n"
                f"Medications: {meds_text}\n"
                f"Instructions: {instructions or user_intent or 'No additional instructions provided.'}"
            )
            result_json = {
                "ok": True,
                "draft_text": draft_body,
                "patient_mrn": patient_mrn,
                "message": "Draft prescription created. Confirm the draft before submitting.",
            }
            return result_json
        except Exception as exc:
            error = str(exc)
            raise
        finally:
            self._audit_execution(
                interaction_id=interaction_id,
                tool_name=self.name,
                user_id=user_id,
                role=role,
                is_write_action=self.is_write_action,
                arguments_json={
                    "patient_mrn": patient_mrn,
                    "medications": medications,
                    "instructions": instructions,
                },
                result_json=result_json,
                error=error,
            )


class SubmitPrescriptionTool(MedAITool):
    name: str = "submit_prescription"
    description: str = (
        "Submit a previously drafted prescription to the EMR after explicit user confirmation. "
        "Requires a confirmation token to proceed."
    )
    args_schema: Type[PrescriptionSubmitInput] = PrescriptionSubmitInput
    tool_category: str = "write"
    is_write_action: bool = True

    def _run(
        self,
        user_id: str,
        role: str,
        draft_text: str,
        patient_mrn: Optional[str] = None,
        confirmation_token: Optional[str] = None,
        note: Optional[str] = None,
        interaction_id: Optional[int] = None,
    ) -> dict:
        result_json = None
        error = None
        token_id_used = confirmation_token
        try:
            if role != "doctor":
                return {
                    "ok": False,
                    "message": "Only doctors may submit prescriptions. If you are a nurse, you may draft a prescription and ask a doctor to submit it.",
                }

            if not confirmation_token:
                token_id = get_confirmation_service().generate(
                    user_id=user_id,
                    role=role,
                    action="submit_prescription",
                    payload={
                        "patient_mrn": patient_mrn,
                        "draft_text": draft_text,
                        "note": note,
                    },
                )
                token_id_used = token_id
                result_json = {
                    "ok": False,
                    "requires_confirmation": True,
                    "confirmation_token": token_id,
                    "message": "Prescription submission requires confirmation. Resubmit this action with the returned token.",
                }
                return result_json

            token_data = get_confirmation_service().validate(
                confirmation_token,
                user_id=user_id,
                action="submit_prescription",
            )
            if not token_data:
                result_json = {
                    "ok": False,
                    "requires_confirmation": True,
                    "message": "The confirmation token is invalid or expired. Generate a new token and try again.",
                }
                return result_json

            stored_payload = token_data.get("payload") or {}
            if stored_payload.get("patient_mrn") != patient_mrn or stored_payload.get("draft_text") != draft_text:
                result_json = {
                    "ok": False,
                    "requires_confirmation": True,
                    "message": "The confirmation token does not match the prescription draft. Generate a new confirmation token for this exact draft.",
                }
                return result_json

            submission_result = submit_prescription(
                doctor_user_id=user_id,
                patient_mrn=patient_mrn or "",
                draft_text=draft_text,
                note=note,
            )
            result_json = {
                "ok": True,
                "message": (
                    "Prescription submitted successfully to the EMR stub. "
                    "In production, integrate with the hospital EMR API for real submission."
                ),
                "submission_result": submission_result,
            }
            return result_json
        except Exception as exc:
            error = str(exc)
            return {
                "ok": False,
                "message": f"Prescription submission failed: {error}",
            }
        finally:
            self._audit_execution(
                interaction_id=interaction_id,
                tool_name=self.name,
                user_id=user_id,
                role=role,
                is_write_action=self.is_write_action,
                arguments_json={
                    "patient_mrn": patient_mrn,
                    "note": note,
                    "confirmation_token": confirmation_token,
                },
                result_json=result_json,
                error=error,
                confirmation_token_id=token_id_used,
            )


def get_tools_for_role(role: str) -> List[BaseTool]:
    tools: List[BaseTool] = [SQLGenTool(), ValidatorTool(), FormatterTool()]
    normalized = (role or "").lower()

    if normalized in {"doctor", "nurse"}:
        tools.append(DraftPrescriptionTool())
    if normalized == "doctor":
        tools.append(SubmitPrescriptionTool())

    return tools
