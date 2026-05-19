"""Service layer orchestrating the Medical Imaging Assist pipeline."""
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List

from app.ai.client import MedicalAIClient
from app.ai.prompts import (
    build_correction_system_prompt,
    build_correction_user_prompt,
    build_matching_system_prompt,
    build_matching_user_prompt,
)
from app.core.config import settings
from app.models.schemas import AssistiveResponse
from app.services.rag_store import RagStore
from app.services.safety_normalizer import normalize_correction, normalize_matching

logger = logging.getLogger(__name__)


def _project_path(relative: str) -> str:
    """Resolve a path relative to the project root."""
    return os.path.join(settings.project_dir, relative)


_PHRASE_SPLIT = re.compile(r"[.,;\n]")


def _extract_phrases(text: str, max_phrases: int = 8) -> List[str]:
    """Split free text into short clauses for per-phrase RAG retrieval."""
    if not text:
        return []
    phrases = [p.strip() for p in _PHRASE_SPLIT.split(text) if p.strip()]
    return phrases[:max_phrases]


class MedicalImagingService:
    """Owns the full pipeline: load files, retrieve, prompt, call AI, normalize, persist."""

    def __init__(self) -> None:
        self._ai_client: MedicalAIClient | None = None
        self.rag = RagStore()
        self.project_dir = settings.project_dir
        self._guide_text = self._load_text_file(settings.terms_guide_file)
        self._schema_text = self._load_text_file(settings.output_schema_file)

    def _get_ai_client(self) -> MedicalAIClient:
        """Lazy-initialize the OpenAI client so non-AI endpoints can run without a key."""
        if self._ai_client is None:
            self._ai_client = MedicalAIClient()
        return self._ai_client

    def _load_text_file(self, relative_path: str) -> str:
        """Read a UTF-8 text file from the project root."""
        filepath = _project_path(relative_path)
        if not os.path.isfile(filepath):
            raise FileNotFoundError(f"Required file not found: {relative_path}")
        with open(filepath, "r", encoding="utf-8") as fh:
            return fh.read()

    def get_terms_summary(self) -> Dict[str, Any]:
        """Return counts of loaded RAG entries WITHOUT calling the AI."""
        return {
            "icd10_count": len(self.rag.icd10),
            "radlex_count": len(self.rag.radlex),
            "embeddings_present": self.rag.embeddings_present(),
        }

    def _retrieve_for_text(self, text: str, k_per_phrase: int = 3) -> tuple[list, list]:
        """Retrieve ICD-10 and RadLex candidates for the union of phrases in `text`."""
        phrases = _extract_phrases(text) or [text]
        icd_seen: Dict[str, Dict[str, Any]] = {}
        radlex_seen: Dict[str, Dict[str, Any]] = {}
        for phrase in phrases:
            for entry in self.rag.retrieve_icd10(phrase, k=k_per_phrase):
                icd_seen.setdefault(entry["code"], entry)
            for entry in self.rag.retrieve_radlex(phrase, k=k_per_phrase):
                radlex_seen.setdefault(entry["id"], entry)
        return list(icd_seen.values()), list(radlex_seen.values())

    def report_correction(
        self,
        doctor_notes: str,
        radiologist_notes: str,
        exam_type: str | None,
        dicom_metadata: Dict[str, Any],
    ) -> AssistiveResponse:
        """Run the full report-correction pipeline."""
        combined_for_rag = f"{doctor_notes}\n{radiologist_notes}"
        icd_candidates, radlex_candidates = self._retrieve_for_text(combined_for_rag)
        logger.info(
            "RAG retrieval: %d ICD-10, %d RadLex candidates", len(icd_candidates), len(radlex_candidates)
        )

        system_prompt = build_correction_system_prompt(
            guide_text=self._guide_text,
            schema_text=self._schema_text,
            icd10_candidates=icd_candidates,
            radlex_candidates=radlex_candidates,
        )
        user_prompt = build_correction_user_prompt(
            doctor_notes=doctor_notes,
            radiologist_notes=radiologist_notes,
            exam_type=exam_type,
            dicom_metadata=dicom_metadata,
        )

        raw = self._get_ai_client().analyze(system_prompt, user_prompt)
        normalized = normalize_correction(
            raw=raw,
            doctor_notes=doctor_notes,
            radiologist_notes=radiologist_notes,
            exam_type=exam_type,
            dicom_metadata=dicom_metadata,
        )

        if settings.persist_output:
            normalized.output_file = self._save_output(normalized, prefix="report_correction")
        return normalized

    def analysis_matching(
        self,
        clinical_report: str,
        ai_image_analysis: Dict[str, Any],
        dicom_metadata: Dict[str, Any],
    ) -> AssistiveResponse:
        """Run the full analysis-matching pipeline."""
        ai_text_blob = json.dumps(ai_image_analysis)
        combined_for_rag = f"{clinical_report}\n{ai_text_blob}"
        icd_candidates, radlex_candidates = self._retrieve_for_text(combined_for_rag)
        logger.info(
            "RAG retrieval: %d ICD-10, %d RadLex candidates", len(icd_candidates), len(radlex_candidates)
        )

        system_prompt = build_matching_system_prompt(
            guide_text=self._guide_text,
            schema_text=self._schema_text,
            icd10_candidates=icd_candidates,
            radlex_candidates=radlex_candidates,
        )
        user_prompt = build_matching_user_prompt(
            clinical_report=clinical_report,
            ai_image_analysis=ai_image_analysis,
            dicom_metadata=dicom_metadata,
        )

        raw = self._get_ai_client().analyze(system_prompt, user_prompt)
        normalized = normalize_matching(
            raw=raw,
            clinical_report=clinical_report,
            ai_image_analysis=ai_image_analysis,
            dicom_metadata=dicom_metadata,
        )

        if settings.persist_output:
            normalized.output_file = self._save_output(normalized, prefix="analysis_matching")
        return normalized

    def _save_output(self, response: AssistiveResponse, prefix: str) -> str:
        """Persist the full response (PHI-bearing) as timestamped JSON in ./output."""
        output_dir = _project_path("output")
        os.makedirs(output_dir, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        filename = f"{prefix}_{timestamp}.json"
        filepath = os.path.join(output_dir, filename)
        with open(filepath, "w", encoding="utf-8") as fh:
            json.dump(response.model_dump(), fh, indent=2)
        logger.info("Saved output to %s", filepath)
        return filepath
