"""
Autofill service — maps raw input into a template's fields using an LLM
(OpenAI). Supports a MOCK_LLM mode for offline testing.
"""

import json
import logging
from typing import Any, Optional

from models.schemas import (
    AutofillResponse,
    FieldValidation,
    Template,
)

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are an experienced radiologist's reporting assistant.
Given a raw clinician dictation or clinical input and a radiology report template,
populate each template field with concise, clinically appropriate text derived
strictly from the input. Do not invent findings. If the input does not address a
field, return an empty string for that field.

Return ONLY a JSON object that maps each template field's `name` to a string
value. No commentary, no markdown code fences."""


class AutofillService:
    def __init__(
        self,
        openai_api_key: Optional[str],
        model: str,
        temperature: float,
        mock_llm: bool = False,
    ):
        self.openai_api_key = openai_api_key
        self.model = model
        self.temperature = temperature
        self.mock_llm = mock_llm
        self._client = None
        self.initialized = False

    def initialize(self) -> None:
        if self.initialized:
            return
        if self.mock_llm:
            logger.warning("Autofill running in MOCK_LLM mode — no OpenAI calls will be made")
            self.initialized = True
            return
        if not self.openai_api_key:
            logger.warning("OPENAI_API_KEY missing — autofill will fail on real requests")
            self.initialized = True
            return

        from openai import OpenAI
        self._client = OpenAI(api_key=self.openai_api_key)
        self.initialized = True
        logger.info("Autofill service initialized with model %s", self.model)

    async def autofill(
        self,
        template: Template,
        input_data: str,
        request_id: Optional[str] = None,
        patient_context: Optional[dict[str, Any]] = None,
    ) -> AutofillResponse:
        if not self.initialized:
            self.initialize()

        if self.mock_llm or self._client is None:
            populated = self._mock_populate(template, input_data)
            confidence = 0.4
        else:
            populated = await self._llm_populate(template, input_data, patient_context)
            confidence = 0.85

        missing_required = [
            f.name for f in template.fields if f.required and not populated.get(f.name)
        ]
        warnings = [
            FieldValidation(
                field_name=name,
                issue="Required field is empty — input did not contain enough information.",
                severity="warning",
            )
            for name in missing_required
        ]
        if missing_required:
            confidence = max(0.0, confidence - 0.1 * len(missing_required))

        rendered = self._render(template, populated)

        return AutofillResponse(
            request_id=request_id,
            template_id=template.template_id,
            template_name=template.name,
            populated_fields=populated,
            rendered_report=rendered,
            missing_required_fields=missing_required,
            warnings=warnings,
            confidence_score=round(confidence, 3),
        )

    async def _llm_populate(
        self,
        template: Template,
        input_data: str,
        patient_context: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        field_spec = [
            {
                "name": f.name,
                "label": f.label,
                "description": f.description,
                "required": f.required,
            }
            for f in template.fields
        ]
        user_payload = {
            "template": {
                "template_id": template.template_id,
                "name": template.name,
                "modality": template.modality,
                "body_region": template.body_region,
                "fields": field_spec,
            },
            "patient_context": patient_context or {},
            "input": input_data,
        }

        response = self._client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
        )
        content = response.choices[0].message.content or "{}"
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            logger.error("LLM returned non-JSON content: %s", content[:200])
            data = {}

        # Coerce to strings and ensure every field key exists.
        populated: dict[str, Any] = {}
        for field in template.fields:
            value = data.get(field.name, "")
            if isinstance(value, list):
                value = "\n".join(str(v) for v in value)
            populated[field.name] = "" if value is None else str(value)
        return populated

    @staticmethod
    def _mock_populate(template: Template, input_data: str) -> dict[str, Any]:
        """Deterministic placeholder content used when MOCK_LLM=true."""
        snippet = input_data.strip().replace("\n", " ")
        snippet = (snippet[:140] + "...") if len(snippet) > 140 else snippet
        out: dict[str, Any] = {}
        for field in template.fields:
            if field.name == "exam":
                out[field.name] = template.name
            elif field.name == "clinical_history":
                out[field.name] = snippet or "Not provided."
            elif field.name == "technique":
                out[field.name] = f"Standard {template.modality} protocol."
            elif field.name == "comparison":
                out[field.name] = "None available."
            elif field.name == "impression":
                out[field.name] = "[MOCK] Impression placeholder — see findings."
            else:
                out[field.name] = ""
        return out

    @staticmethod
    def _render(template: Template, populated: dict[str, Any]) -> str:
        lines = [f"{template.name.upper()}", ""]
        for field in template.fields:
            value = populated.get(field.name, "")
            if value == "":
                value = "Not addressed."
            lines.append(f"{field.label}:")
            lines.append(str(value))
            lines.append("")
        return "\n".join(lines).strip()
