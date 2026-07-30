"""Service layer orchestrating the SepsisSentinel analysis pipeline."""
import json
import logging
import os
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.ai.client import SepsisAIClient
from app.ai.prompts import build_system_prompt, build_user_prompt
from app.services.output_normalizer import normalize_analysis_result

logger = logging.getLogger(__name__)


class SepsisService:
    """Orchestrates patient data loading, prompt building, AI analysis,
    and output saving."""

    def __init__(self):
        """Initialise the service with an AI client."""
        self.ai_client = SepsisAIClient()
        self.project_dir = settings.project_dir

    # ------------------------------------------------------------------
    # File helpers
    # ------------------------------------------------------------------

    def _load_text_file(self, relative_path: str) -> str:
        """Read and return the full text of a file relative to the project dir.

        Args:
            relative_path: Path relative to the project root.

        Returns:
            File contents as a string.

        Raises:
            FileNotFoundError: If the file does not exist.
        """
        filepath = os.path.join(self.project_dir, relative_path)
        if not os.path.isfile(filepath):
            raise FileNotFoundError(f"Required file not found: {relative_path}")
        with open(filepath, "r", encoding="utf-8") as fh:
            return fh.read()

    def _load_patient_file(self, patient_id: int) -> Dict[str, Any]:
        """Load and parse the JSON file for a given sample patient ID.

        Args:
            patient_id: Integer 1, 2, or 3.

        Returns:
            Parsed patient data dict.

        Raises:
            FileNotFoundError: If the patient file is missing.
        """
        filename = f"patient_00{patient_id}.json"
        relative_path = os.path.join("sample_data", filename)
        filepath = os.path.join(self.project_dir, relative_path)
        if not os.path.isfile(filepath):
            raise FileNotFoundError(
                f"Patient file not found: {relative_path}. "
                "Ensure the sample_data folder contains the patient JSON files."
            )
        with open(filepath, "r", encoding="utf-8") as fh:
            return json.load(fh)

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def list_patients(self) -> List[Dict[str, Any]]:
        """Return summary info for all available sample patients.

        Returns:
            List of dicts with patient_id, name, and admission_reason.
        """
        patients = []
        for pid in (1, 2, 3):
            try:
                data = self._load_patient_file(pid)
                info = data["patient_info"]
                patients.append({
                    "patient_id": pid,
                    "name": info["name"],
                    "admission_reason": info["admission_reason"],
                })
            except (FileNotFoundError, KeyError) as exc:
                logger.warning("Could not load patient %d: %s", pid, exc)
                patients.append({
                    "patient_id": pid,
                    "name": "(data unavailable)",
                    "admission_reason": "(data unavailable)",
                })
        return patients

    def get_patient(self, patient_id: int) -> Dict[str, Any]:
        """Return the full payload for a single sample patient."""
        return {
            "patient_id": patient_id,
            "patient_data": self._load_patient_file(patient_id),
        }

    def analyze_sample_patient(self, patient_id: int) -> Dict[str, Any]:
        """Run analysis for a built-in sample patient."""
        result = self.analyze_patient(patient_id=patient_id)
        result["source"] = "sample"
        return result

    def analyze_custom_patient(
        self, patient_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Run analysis for custom patient data submitted by the client."""
        result = self.analyze_patient(patient_data=patient_data)
        result["source"] = "custom"
        return result

    def analyze_patient(
        self,
        patient_id: Optional[int] = None,
        patient_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Run the full sepsis analysis pipeline.

        Exactly one of patient_id or patient_data must be provided.

        Args:
            patient_id: Sample patient ID (1-3) to load from disk.
            patient_data: Raw patient data dict (patient_info + hourly_data).

        Returns:
            Dict with keys: analysis (the GPT result), output_file (save path),
            and patient_id.

        Raises:
            ValueError: If neither or both arguments are provided.
            FileNotFoundError: If patient file is missing.
        """
        if patient_id is None and patient_data is None:
            raise ValueError(
                "Provide either patient_id (1-3) or patient_data."
            )
        if patient_id is not None and patient_data is not None:
            raise ValueError(
                "Provide only one of patient_id or patient_data, not both."
            )

        # Load patient data
        if patient_id is not None:
            logger.info("Loading sample patient %d ...", patient_id)
            patient_data = self._load_patient_file(patient_id)

        # Load context and schema
        context = self._load_text_file("context.txt")
        schema = self._load_text_file("output_schema.json")

        # Build prompts
        system_prompt = build_system_prompt(context, schema)
        user_prompt = build_user_prompt(patient_data)

        # Call AI
        logger.info("Sending data to GPT-4o for analysis ...")
        raw_result = self.ai_client.analyze(system_prompt, user_prompt)
        result = normalize_analysis_result(raw_result, patient_data)

        # Save output
        output_file = self._save_output(result, patient_id)
        logger.info("Analysis complete. Output saved to %s", output_file)

        return {
            "patient_id": patient_id,
            "analysis": result,
            "output_file": output_file,
            "source": "sample" if patient_id is not None else "custom",
        }

    def _save_output(
        self, result: Dict[str, Any], patient_id: Optional[int]
    ) -> str:
        """Save the analysis result to the proper_output directory.

        Args:
            result: The analysis result dict.
            patient_id: Optional patient ID for the filename.

        Returns:
            Absolute path to the saved file.
        """
        output_dir = os.path.join(self.project_dir, "proper_output")
        os.makedirs(output_dir, exist_ok=True)

        if patient_id is not None:
            filename = f"proper_output_patient_{patient_id}.json"
        else:
            filename = "proper_output_custom.json"

        filepath = os.path.join(output_dir, filename)
        with open(filepath, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2)
        return filepath
