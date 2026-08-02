"""Main service orchestrator for Direct QA flow."""

import logging
import re
from typing import Dict, Any, Optional, List
from ...domain.entities import PatientRecord, OnsiteDoc, DischargeReport, ReportTemplate, QualityRules
from ...domain.rules import load_rules_from_dict
from ...domain.rules import load_quality_rules
from .parser import DischargeReportParser
from .normalizer import DischargeReportNormalizer
from .conflict_resolver import ConflictResolver
from .rule_engine import RuleEngine
from .merge_utils import merge_findings, merge_medications, deep_merge_content, normalize_content_sections, filter_resolved_findings
from .scoring import QAScorer
from ...core.prompt_runner import PromptRunner
from ...core.response_validator import ResponseValidator
from ...security.anonymization_check import AnonymizationChecker

# Set up logging - ensure it outputs to console
logger = logging.getLogger(__name__)
if not logger.handlers:  # Only configure if not already configured
    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)


class DischargeQAService:
    """Orchestrates the Direct QA flow."""
    
    def __init__(
        self,
        prompt_runner: Optional[PromptRunner] = None,
        validator: Optional[ResponseValidator] = None
    ):
        """Initialize service.
        
        Args:
            prompt_runner: Optional prompt runner (creates new one if not provided)
            validator: Optional response validator (creates new one if not provided)
        """
        self.parser = DischargeReportParser()
        self.normalizer = DischargeReportNormalizer()
        self.conflict_resolver = ConflictResolver()
        self.rule_engine = RuleEngine(self.conflict_resolver)
        self.scorer = QAScorer()
        self.prompt_runner = prompt_runner or PromptRunner()
        self.validator = validator or ResponseValidator()
        self.phi_checker = AnonymizationChecker()
    
    def perform_qa(
        self,
        discharge_report: Any,
        patient_record: Dict[str, Any],
        onsite_docs: List[Dict[str, Any]],
        report_template: Optional[Dict[str, Any]] = None,
        quality_rules: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Perform Direct QA on discharge report.
        
        Args:
            discharge_report: Discharge report (text or JSON)
            patient_record: Patient record dictionary
            onsite_docs: List of onsite document dictionaries
            report_template: Optional report template
            quality_rules: Optional quality rules dictionary
            
        Returns:
            QA results dictionary
        """
        # Step 1: Parse discharge report
        logger.debug("Step 1: Parsing discharge report...")
        quality_rules = self._resolve_quality_rules(quality_rules)
        parsed_report = self.parser.parse(discharge_report, report_template)
        logger.debug(f"Parsed report format: {parsed_report.get('format')}")
        logger.debug(f"Parsed report structure_used: {parsed_report.get('structure_used')}")
        
        # Step 2: Normalize content
        logger.debug("Step 2: Normalizing content...")
        normalized_content = self._normalize_content(parsed_report["content"], report_template)
        normalized_content = normalize_content_sections(normalized_content)
        parsed_report["content"] = normalized_content
        
        # Debug: Check medications after normalization
        if "medications" in normalized_content:
            logger.debug(f"Medications after normalization: {normalized_content['medications']}")
            if "discharge_medications" in normalized_content["medications"]:
                meds = normalized_content["medications"]["discharge_medications"]
                logger.debug(f"Number of discharge medications: {len(meds)}")
                if meds:
                    logger.debug(f"First medication sample: {meds[0]}")
                    # Check if properly parsed
                    first_med = meds[0] if isinstance(meds[0], dict) else {}
                    if first_med.get("dose") or first_med.get("frequency"):
                        logger.debug("✓ Medications are properly parsed (have dose/frequency)")
                    else:
                        logger.warning("⚠ Medications NOT properly parsed (missing dose/frequency)")
        
        # Store normalized content for later merging (deep copy to avoid modification)
        import copy
        self._normalized_content = copy.deepcopy(normalized_content)
        logger.debug("Stored normalized_content for later merging")
        
        # Step 3: Run AI-powered QA
        try:
            qa_result = self.prompt_runner.run_qa(
                discharge_report=discharge_report,
                patient_record=patient_record,
                onsite_docs=onsite_docs,
                report_template=report_template,
                quality_rules=quality_rules
            )
        except Exception as e:
            # Fallback to basic structure if AI fails
            qa_result = self._create_fallback_result(parsed_report)
            qa_result["summary"] = f"QA analysis encountered an error: {str(e)}"
        
        # Step 4: Merge normalized parsed_report with AI response early
        self._merge_normalized_content(qa_result, getattr(self, "_normalized_content", {}))
        merged_content = normalize_content_sections(
            qa_result.get("parsed_report", {}).get("content", parsed_report["content"])
        )
        qa_result["parsed_report"]["content"] = merged_content

        # Step 5: Run deterministic rule-engine checks on merged content
        rule_findings = self.rule_engine.evaluate(
            content=merged_content,
            patient_record=patient_record,
            onsite_docs=onsite_docs,
            report_template=report_template,
            quality_rules=quality_rules,
        )
        qa_result = merge_findings(qa_result, rule_findings)
        qa_result = filter_resolved_findings(qa_result, merged_content)
        qa_result = self.validator.fix_response(qa_result)

        # Step 6: Post-process (scoring, conflict resolution)
        qa_result = self._post_process(qa_result, patient_record, onsite_docs)

        # Step 7: Final schema validation
        validation_note = None
        is_valid, error_msg = self.validator.validate(qa_result)
        if not is_valid:
            qa_result = self.validator.fix_response(qa_result)
            qa_result = self._post_process(qa_result, patient_record, onsite_docs)
            is_valid, error_msg = self.validator.validate(qa_result)
            if not is_valid:
                validation_note = error_msg
        if validation_note:
            qa_result["summary"] += f" Response validation issues: {validation_note}"
        
        # Step 8: Check for PHI
        phi_issues = self.phi_checker.check_output(qa_result)
        if phi_issues:
            qa_result = self.phi_checker.sanitize_output(qa_result)
            qa_result = self.validator.fix_response(qa_result)
            qa_result["summary"] += " PHI detected and redacted."
        
        # Step 9: Ensure parsed_report format/structure_used is correct
        if "parsed_report" in qa_result:
            qa_result["parsed_report"]["format"] = parsed_report["format"]
            qa_result["parsed_report"]["structure_used"] = parsed_report["structure_used"]
            qa_result["parsed_report"] = self.validator._fix_parsed_report(qa_result["parsed_report"])
        
        # Step 10: Final cleanup - remove any invalid medications that might have slipped through
        logger.debug("Step 9: Final cleanup of medications...")
        if "parsed_report" in qa_result and "content" in qa_result["parsed_report"]:
            final_content = qa_result["parsed_report"]["content"]
            if "medications" in final_content and "discharge_medications" in final_content["medications"]:
                final_meds = final_content["medications"]["discharge_medications"]
                logger.debug(f"Final cleanup: Found {len(final_meds)} medications to check")
                if final_meds:
                    logger.debug(f"Final cleanup: Sample medication before cleanup: {final_meds[0]}")
                cleaned_final_meds = []
                removed_count = 0
                for med in final_meds:
                    if not isinstance(med, dict):
                        logger.debug(f"Final cleanup: Skipping non-dict medication: {med}")
                        removed_count += 1
                        continue
                    name = med.get("name", "").strip()
                    # Remove invalid entries
                    if not name or name == ":" or re.match(r"^[:\-\s]+$", name):
                        logger.debug(f"Final cleanup: Removing invalid medication: '{name[:50]}'")
                        removed_count += 1
                        continue
                    # Remove header fragments
                    if re.search(r"(?i)^(on\s+discharge|discharge)[:\s]*$", name) and len(name) < 25:
                        logger.debug(f"Final cleanup: Removing header fragment: '{name[:50]}'")
                        removed_count += 1
                        continue
                    # Specifically catch "s on Discharge:" variations
                    if name == "s on Discharge:" or name.startswith("s on Discharge") or name.endswith("s on Discharge:"):
                        logger.debug(f"Final cleanup: Removing 's on Discharge' variant: '{name[:50]}'")
                        removed_count += 1
                        continue
                    # Remove medications that still have the raw format (start with "- " and have no parsed fields)
                    # These should have been normalized, so if they're still in raw format, they're likely duplicates or errors
                    if name.startswith("- ") and not med.get("dose") and not med.get("frequency") and not med.get("route"):
                        # Check if this looks like it should have been parsed (contains dose pattern)
                        if re.search(r"(?i)\d+\s*(?:mg|mcg|g|ml|units?)", name):
                            logger.debug(f"Final cleanup: Removing unparsed medication string (should have been normalized): '{name[:50]}'")
                            removed_count += 1
                            continue
                    cleaned_final_meds.append(med)
                if removed_count > 0:
                    logger.debug(f"Final cleanup: Removed {removed_count} invalid medications (kept {len(cleaned_final_meds)})")
                    final_content["medications"]["discharge_medications"] = cleaned_final_meds
                    if cleaned_final_meds:
                        logger.debug(f"Final cleanup: Sample medication after cleanup: {cleaned_final_meds[0]}")
                else:
                    logger.debug(f"Final cleanup: All {len(final_meds)} medications are valid")
            else:
                logger.debug("Final cleanup: No discharge_medications found in final content")
        else:
            logger.debug("Final cleanup: No parsed_report.content found")
        
        return qa_result
    
    def _normalize_content(self, content: Dict[str, Any], template: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Normalize report content."""
        normalized = content.copy()
        
        # Normalize medications
        if "medications" in normalized:
            meds = normalized["medications"]
            if "discharge_medications" in meds:
                meds["discharge_medications"] = self.normalizer.normalize_medications(
                    meds["discharge_medications"]
                )
            if "home_medications" in meds:
                meds["home_medications"] = self.normalizer.normalize_medications(
                    meds["home_medications"]
                )
        
        # Normalize vitals
        if "vitals_and_key_results" in normalized:
            vitals = normalized["vitals_and_key_results"]
            if "vitals_last" in vitals:
                vitals["vitals_last"] = self.normalizer.normalize_vitals(vitals["vitals_last"])
        
        # Normalize section names
        normalized = self.normalizer.normalize_section_names(normalized, template)
        
        return normalized
    
    def _merge_normalized_content(self, qa_result: Dict[str, Any], normalized_content: Dict[str, Any]) -> None:
        """Merge parser-normalized content into the AI parsed report."""
        logger.debug("Merging normalized content with AI response...")
        if "parsed_report" not in qa_result:
            qa_result["parsed_report"] = {
                "format": "text",
                "structure_used": "standard",
                "content": {},
                "unmapped_content": [],
            }
        if "content" not in qa_result["parsed_report"]:
            qa_result["parsed_report"]["content"] = {}

        qa_result["parsed_report"]["content"] = deep_merge_content(
            qa_result["parsed_report"]["content"],
            normalized_content,
        )

    def _resolve_quality_rules(self, quality_rules: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Load default quality rules when none are provided."""
        if quality_rules:
            return quality_rules
        return load_quality_rules().model_dump()

    def _post_process(
        self,
        qa_result: Dict[str, Any],
        patient_record: Dict[str, Any],
        onsite_docs: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Post-process QA results (scoring, conflict resolution)."""
        qa_result["overall_score"] = self.scorer.calculate_score(
            qa_result.get("errors", []),
            qa_result.get("missing_items", []),
            qa_result.get("inconsistencies", [])
        )
        qa_result["summary"] = self.scorer.generate_summary(
            qa_result["overall_score"],
            qa_result.get("errors", []),
            qa_result.get("missing_items", []),
            qa_result.get("inconsistencies", [])
        )
        
        # Ensure IDs are set
        qa_result = self._assign_ids(qa_result)
        
        return qa_result
    
    def _assign_ids(self, qa_result: Dict[str, Any]) -> Dict[str, Any]:
        """Assign deterministic IDs to items."""
        counter = {"ERR": 1, "MISS": 1, "INC": 1, "FIX": 1}
        
        # Assign error IDs
        for error in qa_result.get("errors", []):
            if "id" not in error or not error["id"]:
                error["id"] = f"ERR-{counter['ERR']:03d}"
                counter["ERR"] += 1
        
        # Assign missing item IDs
        for item in qa_result.get("missing_items", []):
            if "id" not in item or not item["id"]:
                item["id"] = f"MISS-{counter['MISS']:03d}"
                counter["MISS"] += 1
        
        # Assign inconsistency IDs
        for inc in qa_result.get("inconsistencies", []):
            if "id" not in inc or not inc["id"]:
                inc["id"] = f"INC-{counter['INC']:03d}"
                counter["INC"] += 1
        
        # Assign correction IDs
        for fix in qa_result.get("recommended_corrections", []):
            if "id" not in fix or not fix["id"]:
                fix["id"] = f"FIX-{counter['FIX']:03d}"
                counter["FIX"] += 1
        
        return qa_result
    
    def _create_fallback_result(self, parsed_report: Dict[str, Any]) -> Dict[str, Any]:
        """Create fallback result structure."""
        return {
            "qa_method": "direct_qa",
            "overall_score": 0,
            "summary": "QA analysis could not be completed.",
            "parsed_report": parsed_report,
            "errors": [],
            "missing_items": [],
            "inconsistencies": [],
            "recommended_corrections": []
        }

