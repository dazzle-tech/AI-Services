"""Service for parsing OCR text into structured JSON using Ollama."""
import json
import logging
import re
import subprocess
import time
from textwrap import dedent
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


class ParsingService:
    """Parse free-form OCR text into structured fields."""

    def __init__(self) -> None:
        self.command = settings.ollama_command
        self.model = settings.ollama_model
        self.timeout_seconds = settings.ollama_timeout_seconds

    def parse_text(self, extracted_text: str) -> dict[str, Any]:
        cleaned_text = "\n".join(
            line.strip() for line in extracted_text.splitlines() if line.strip()
        )
        prompt = self._build_prompt(cleaned_text)
        logger.info("Sending parse request to Ollama model=%s", self.model)

        start_time = time.monotonic()
        process = subprocess.run(
            [self.command, "run", self.model],
            input=prompt.encode("utf-8"),
            capture_output=True,
            timeout=self.timeout_seconds,
            check=False,
        )
        elapsed_seconds = time.monotonic() - start_time
        logger.info("Ollama request finished in %.2fs (exit_code=%s)", elapsed_seconds, process.returncode)

        if process.returncode != 0:
            stderr = (process.stderr or b"").decode("utf-8", errors="replace").strip()
            raise RuntimeError(
                f"Ollama command failed with exit code {process.returncode}: {stderr}"
            )

        stdout = (process.stdout or b"").decode("utf-8", errors="replace")
        return self._extract_json(stdout)

    def _build_prompt(self, cleaned_text: str) -> str:
        return dedent(
            f"""
            You are a strict JSON parser. I will give you OCR text from a passport/ID.
            Return ONLY a valid JSON object with these fields:
            - Type
            - Document Number
            - Surname / Family Name
            - Given Names
            - Nationality
            - Date of Birth
            - Sex
            - Place of Birth

            Do not include explanations or extra text. If a field is missing, return an empty string.

            OCR Text:
            {cleaned_text}
            """
        ).strip()

    def _extract_json(self, model_output: str) -> dict[str, Any]:
        # Accept plain JSON, fenced JSON, or text containing a JSON block.
        cleaned = model_output.strip()
        cleaned = re.sub(
            r"^```(?:json)?\s*|\s*```$",
            "",
            cleaned,
            flags=re.IGNORECASE | re.DOTALL,
        ).strip()

        if not (cleaned.startswith("{") and cleaned.endswith("}")):
            match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
            if match:
                cleaned = match.group(0)

        try:
            parsed = json.loads(cleaned)
            if not isinstance(parsed, dict):
                raise ValueError("Parsed JSON is not an object")
            return parsed
        except json.JSONDecodeError as exc:
            logger.error("Model output was not valid JSON: %s", cleaned[:500])
            raise ValueError("Model did not return valid JSON") from exc
