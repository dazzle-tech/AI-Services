"""Service for parsing OCR text into structured JSON using OpenAI."""
import logging
import time
from textwrap import dedent
from typing import Any

from app.ai.client import StructuredOutputClient
from app.core.config import settings

logger = logging.getLogger(__name__)


class ParsingService:
    """Parse free-form OCR text into structured fields."""

    def __init__(self) -> None:
        self.client = StructuredOutputClient()
        self.model = settings.openai_model

    def parse_text(self, extracted_text: str) -> dict[str, Any]:
        cleaned_text = "\n".join(
            line.strip() for line in extracted_text.splitlines() if line.strip()
        )
        return self._run_prompt(
            system_prompt=self._system_prompt(),
            user_prompt=self._build_prompt(cleaned_text),
        )

    def parse_prompt(self, prompt: str) -> dict[str, Any]:
        cleaned_prompt = prompt.strip()
        return self._run_prompt(
            system_prompt="You are a strict JSON parser. Return only a valid JSON object with no extra text.",
            user_prompt=cleaned_prompt,
        )

    def _run_prompt(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        logger.info("Sending parse request to OpenAI model=%s", self.model)
        start_time = time.monotonic()
        result = self.client.generate_json(system_prompt=system_prompt, user_prompt=user_prompt)
        elapsed_seconds = time.monotonic() - start_time
        logger.info("Structured extraction finished in %.2fs", elapsed_seconds)
        return result

    def _system_prompt(self) -> str:
        return dedent(
            """
            You are a strict JSON parser for OCR text extracted from passports and ID documents.
            Return only a valid JSON object and no surrounding explanation or markdown.
            """
        ).strip()

    def _build_prompt(self, cleaned_text: str) -> str:
        return dedent(
            f"""
            Extract fields from this OCR text from a passport or ID card.
            Return ONLY a valid JSON object with exactly these fields:
            - Type
            - Document Number
            - Surname / Family Name
            - Given Names
            - Nationality
            - Date of Birth
            - Sex
            - Place of Birth

            Type normalization rules:
            - If the OCR text indicates an identification card, identity card, ID card, or contains phrases like "IDENTIFICATION CARD" or "ID NUMBER", set "Type" to "ID".
            - If the OCR text indicates a passport, set "Type" to "Passport".
            - If the document type cannot be inferred, return "undefined" for "Type".

            Do not include explanations or extra text.
            If a field is missing or cannot be inferred confidently, return "undefined".
            Never return empty strings.

            OCR Text:
            {cleaned_text}
            """
        ).strip()
