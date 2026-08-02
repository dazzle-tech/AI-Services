"""Prompt runner for executing QA prompts."""

import json
from pathlib import Path
from typing import Dict, Any, Optional
from .openai_client import OpenAIClient
from ..utils.json_utils import extract_json_from_text


class PromptRunner:
    """Loads and executes prompts using OpenAI."""
    
    def __init__(self, openai_client: Optional[OpenAIClient] = None):
        """Initialize prompt runner.
        
        Args:
            openai_client: Optional OpenAI client (creates new one if not provided)
        """
        self.client = openai_client or OpenAIClient()
        self.prompt_template = self._load_prompt_template()
    
    def _load_prompt_template(self) -> str:
        """Load prompt template from file."""
        prompt_file = Path(__file__).parent.parent.parent / "docs" / "prompts" / "discharge_qa_direct.prompt.md"
        
        if prompt_file.exists():
            with open(prompt_file, "r", encoding="utf-8") as f:
                return f.read()
        else:
            # Fallback to basic prompt
            return "You are a clinical discharge report QA engine. Analyze the provided discharge report and return JSON output."
    
    def run_qa(
        self,
        discharge_report: Any,
        patient_record: Dict[str, Any],
        onsite_docs: list,
        report_template: Optional[Dict[str, Any]] = None,
        quality_rules: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Run QA analysis using the prompt.
        
        Args:
            discharge_report: Discharge report content (text or JSON)
            patient_record: Patient record dictionary
            onsite_docs: List of onsite document dictionaries
            report_template: Optional report template
            quality_rules: Optional quality rules
            
        Returns:
            QA results as dictionary
        """
        # Build prompt with inputs
        prompt = self._build_prompt(
            discharge_report,
            patient_record,
            onsite_docs,
            report_template,
            quality_rules
        )
        
        # Execute prompt
        response_text = self.client.complete(
            prompt=prompt,
            temperature=0.3,
            max_tokens=4000
        )
        
        # Extract JSON from response
        result = extract_json_from_text(response_text)
        
        if not isinstance(result, dict):
            raise ValueError("AI response is not valid JSON")
        
        return result
    
    def _build_prompt(
        self,
        discharge_report: Any,
        patient_record: Dict[str, Any],
        onsite_docs: list,
        report_template: Optional[Dict[str, Any]],
        quality_rules: Optional[Dict[str, Any]]
    ) -> str:
        """Build prompt with all inputs."""
        prompt_parts = [self.prompt_template]
        prompt_parts.append("\n\n=== INPUTS ===\n\n")
        
        # Add discharge report
        prompt_parts.append("DISCHARGE_REPORT:\n")
        if isinstance(discharge_report, str):
            prompt_parts.append(discharge_report)
        else:
            prompt_parts.append(json.dumps(discharge_report, indent=2))
        prompt_parts.append("\n\n")
        
        # Add patient record
        prompt_parts.append("PATIENT_RECORD:\n")
        prompt_parts.append(json.dumps(patient_record, indent=2))
        prompt_parts.append("\n\n")
        
        # Add onsite docs
        prompt_parts.append("ONSITE_DOCS:\n")
        prompt_parts.append(json.dumps(onsite_docs, indent=2))
        prompt_parts.append("\n\n")
        
        # Add template if provided
        if report_template:
            prompt_parts.append("REPORT_TEMPLATE:\n")
            prompt_parts.append(json.dumps(report_template, indent=2))
            prompt_parts.append("\n\n")
        
        # Add quality rules if provided
        if quality_rules:
            prompt_parts.append("QUALITY_RULES:\n")
            prompt_parts.append(json.dumps(quality_rules, indent=2))
            prompt_parts.append("\n\n")
        
        prompt_parts.append("=== END INPUTS ===\n\n")
        prompt_parts.append("Now perform Direct QA using the provided inputs and return ONLY the JSON output.")

        prompt = "".join(prompt_parts)
        if self._uses_qwen3_thinking_model():
            prompt += "\n\n/no_think"

        return prompt

    def _uses_qwen3_thinking_model(self) -> bool:
        model_name = (self.client.model or "").lower()
        return "qwen3" in model_name or "qwen" in model_name

