"""
Discharge Report Generation Service using OpenAI GPT-4
Generates discharge summaries from clinical documentation.
"""

import os
import json
import logging
import re
from difflib import SequenceMatcher
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime
from openai import OpenAI  # Import the OpenAI client class

logger = logging.getLogger(__name__)

from models.schemas import (
    DischargeReportSection,
    DischargeReportResponse,
    PatientRecord,
    ClinicalDocumentation,
    ReportTemplate
)
import config


class DischargeReportGenerator:
    """AI-powered discharge report generator using OpenAI."""
    
    def __init__(self):
        self.initialized = False
        self.openai_api_key = config.OPENAI_API_KEY
        self.client = None  # OpenAI client instance
        
        if not self.openai_api_key:
            logger.warning("OPENAI_API_KEY not configured for discharge reports")
        
        self.model = config.OPENAI_MODEL
        self.temperature = 0.2  # Slightly higher for more natural medical writing
        self.timeout = config.OPENAI_TIMEOUT
        
    def initialize(self):
        """Initialize the service."""
        if not self.initialized:
            if self.openai_api_key:
                # Initialize OpenAI client (NEW API - v1.0+)
                # Only pass base_url when set; empty env values make the SDK fail.
                client_kwargs = {
                    "api_key": self.openai_api_key,
                    "timeout": config.OPENAI_TIMEOUT,
                    "max_retries": config.OPENAI_MAX_RETRIES,
                }
                if config.OPENAI_BASE_URL:
                    client_kwargs["base_url"] = config.OPENAI_BASE_URL
                self.client = OpenAI(**client_kwargs)
            self.initialized = True
            logger.info("Discharge Report Generator initialized")
    
    # =========================================================================
    # Main Generation Method
    # =========================================================================
    
    async def generate_discharge_report(
        self,
        patient_record: PatientRecord,
        clinical_documentation: ClinicalDocumentation,
        report_template: Optional[ReportTemplate] = None,
        generation_mode: str = "template"
    ) -> DischargeReportResponse:
        """
        Generate discharge report using AI.
        
        Args:
            patient_record: Anonymized patient demographics and diagnosis
            clinical_documentation: Progress notes, admission notes, etc.
            report_template: Optional template structure
            generation_mode: "template" or "freeform"
        
        Returns:
            DischargeReportResponse with structured sections and full text
        """
        
        if not self.initialized:
            self.initialize()
        
        # Build prompt based on mode
        if generation_mode == "template" and report_template:
            prompt = self._build_template_prompt(
                patient_record,
                clinical_documentation,
                report_template
            )
        else:
            prompt = self._build_freeform_prompt(
                patient_record,
                clinical_documentation
            )
        
        # Call OpenAI
        try:
            report_sections = await self._call_openai_for_report(prompt, generation_mode)
        except Exception as e:
            logger.error(f"OpenAI API Error: {e}", exc_info=True)
            report_sections = self._create_fallback_report(str(e))

        # Post-generation safety checks
        report_sections = self._post_process_sections(
            report_sections=report_sections,
            patient_record=patient_record,
            clinical_documentation=clinical_documentation,
            report_template=report_template,
        )
        
        # Assemble full report text
        full_report_text = self._assemble_full_report(
            report_sections,
            patient_record
        )
        
        # Calculate confidence
        confidence_score = self._calculate_confidence(report_sections)
        
        # Create response
        disclaimer = (
            "⚠️ IMPORTANT: This discharge summary was AI-generated and requires "
            "physician review and approval before finalization. All clinical details "
            "must be verified against source documentation. This is a DRAFT only."
        )
        
        return DischargeReportResponse(
            patient_id=patient_record.patient_id,
            generation_timestamp=datetime.now().isoformat(),
            generation_mode=generation_mode,
            report_sections=report_sections,
            full_report_text=full_report_text,
            template_used=report_template.dict() if report_template else None,
            confidence_score=confidence_score,
            disclaimer=disclaimer,
            requires_physician_review=True
        )
    
    # =========================================================================
    # Prompt Building
    # =========================================================================
    
    def _build_template_prompt(
        self,
        patient: PatientRecord,
        docs: ClinicalDocumentation,
        template: ReportTemplate
    ) -> str:
        """Build prompt for template-based generation."""
        
        prompt = f"""You are an expert medical documentation AI creating a discharge summary.

# PATIENT INFORMATION

**Patient ID:** {patient.patient_id}
**Age:** {patient.age} years
**Gender:** {patient.gender}
**Admission Date:** {patient.admission_date}
**Discharge Date:** {patient.discharge_date or "Not yet discharged"}

**Primary Diagnosis:** {patient.primary_diagnosis}

**Secondary Diagnoses:**
{self._format_list(patient.secondary_diagnoses)}

**Allergies:** {', '.join(patient.allergies) if patient.allergies else 'NKDA'}

**Medications on Admission:**
{self._format_medications(patient.medications_on_admission)}

# CLINICAL DOCUMENTATION

## Admission Note
{docs.admission_notes or "Not provided"}

## Progress Notes
{self._format_progress_notes(docs.progress_notes)}

## Procedures Performed
{self._format_procedures(docs.procedures_performed)}

## Laboratory Results
{json.dumps(docs.lab_results, indent=2)}

## Imaging Results
{self._format_imaging(docs.imaging_results)}

## Consultation Notes
{self._format_list(docs.consultation_notes)}

## Prior Discharge Summaries
{self._format_list(docs.prior_discharge_summaries)}

# REPORT TEMPLATE

**Template Name:** {template.template_name}
**Required Sections:**
{self._format_list(template.sections)}

**Required Fields:**
{self._format_list(template.required_fields)}

# YOUR TASK

Generate a complete discharge summary following the template structure provided. For each section:

1. Synthesize information from the clinical documentation
2. Write in professional medical language
3. Be concise but comprehensive
4. Include specific dates, values, and clinical details
5. Ensure continuity of care information is clear

Return your response as a JSON object with a "sections" array:

{self._build_section_example_json(
    section_names=template.sections,
    source_groups=[
        ["admission_notes", "progress_notes"],
        ["progress_notes", "procedures"]
    ]
)}

# IMPORTANT GUIDELINES

- Write in past tense for completed care
- Use standard medical abbreviations appropriately
- Include quantitative data (lab values, vitals) when relevant
- Maintain professional, objective tone
- If information is missing or unclear, note "Information not available in provided documentation"
- Confidence score should reflect data quality (0.0-1.0)
- If allergies are documented, ensure they appear in an appropriate section. If the template includes an "Allergies" section, place them there. Otherwise include them in "Discharge Diagnosis" or the closest matching section so they are never omitted.

Generate the discharge summary now as JSON:"""
        
        return prompt
    
    def _build_freeform_prompt(
        self,
        patient: PatientRecord,
        docs: ClinicalDocumentation
    ) -> str:
        """Build prompt for freeform generation."""
        
        prompt = f"""You are an expert medical documentation AI creating a comprehensive discharge summary.

# PATIENT INFORMATION

**Patient ID:** {patient.patient_id}
**Age:** {patient.age} years
**Gender:** {patient.gender}
**Admission Date:** {patient.admission_date}
**Discharge Date:** {patient.discharge_date or "Not yet discharged"}

**Primary Diagnosis:** {patient.primary_diagnosis}

**Secondary Diagnoses:**
{self._format_list(patient.secondary_diagnoses)}

**Allergies:** {', '.join(patient.allergies) if patient.allergies else 'NKDA'}

**Medications on Admission:**
{self._format_medications(patient.medications_on_admission)}

# CLINICAL DOCUMENTATION

## Admission Note
{docs.admission_notes or "Not provided"}

## Progress Notes
{self._format_progress_notes(docs.progress_notes)}

## Procedures Performed
{self._format_procedures(docs.procedures_performed)}

## Laboratory Results
{json.dumps(docs.lab_results, indent=2)}

## Imaging Results
{self._format_imaging(docs.imaging_results)}

## Consultation Notes
{self._format_list(docs.consultation_notes)}

# YOUR TASK

Generate a complete, professional discharge summary with these standard sections:

1. **Chief Complaint** - Why patient was admitted
2. **History of Present Illness** - Detailed presentation
3. **Past Medical History** - Relevant history
4. **Hospital Course** - Narrative of hospitalization
5. **Procedures and Interventions** - What was done
6. **Laboratory and Imaging Findings** - Key results
7. **Discharge Diagnosis** - Final diagnoses
8. **Discharge Medications** - Medications at discharge
9. **Discharge Instructions** - Patient education and follow-up
10. **Follow-Up** - Appointments and monitoring needed

Return as JSON object with "sections" array:

{self._build_section_example_json(
    section_names=["Section 1", "Section 2"],
    source_groups=[
        ["admission_notes"],
        ["progress_notes"]
    ]
)}

# GUIDELINES

- Professional medical language
- Chronological narrative for hospital course
- Include specific clinical details and values
- Clear discharge instructions
- Confidence based on documentation quality
- Document any known allergies explicitly. If an "Allergies" or "Discharge Diagnosis" section is present, include them there so they are not dropped.

Generate the comprehensive discharge summary now:"""
        
        return prompt
    
    # =========================================================================
    # OpenAI API Call (FIXED FOR v1.0+)
    # =========================================================================
    
    async def _call_openai_for_report(
        self,
        prompt: str,
        mode: str
    ) -> List[DischargeReportSection]:
        """Call OpenAI and parse response."""
        
        if not self.client:
            raise Exception("OpenAI client not initialized")
        
        try:
            prompt_length = len(prompt)
            logger.info(
                "Calling discharge report generation using model %s base_url=%s timeout=%ss prompt_length=%s",
                self.model,
                config.OPENAI_BASE_URL,
                self.timeout,
                prompt_length,
            )
            # Call OpenAI API using the new client
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert medical documentation AI. You create accurate, professional discharge summaries from clinical documentation. Always respond with valid JSON."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=self.temperature,
                response_format={"type": "json_object"},
                timeout=self.timeout,
            )
            
            content = response.choices[0].message.content
            
            # Parse JSON
            data = json.loads(content)
            
            # Handle different response structures
            if isinstance(data, dict):
                if "sections" in data:
                    sections_data = data["sections"]
                elif "report_sections" in data:
                    sections_data = data["report_sections"]
                else:
                    # Assume the entire dict is a single section
                    sections_data = [data]
            elif isinstance(data, list):
                sections_data = data
            else:
                sections_data = []
            
            # Convert to DischargeReportSection objects
            sections = []
            for section_data in sections_data:
                try:
                    section = DischargeReportSection(
                        section_name=section_data.get("section_name", "Untitled Section"),
                        content=section_data.get("content", ""),
                        confidence=section_data.get("confidence", 0.8),
                        sources=section_data.get("sources", [])
                    )
                    sections.append(section)
                except Exception as e:
                    logger.warning(f"Error parsing section: {e}")
                    continue
            
            return sections
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON Parse Error: {e}")
            logger.debug(f"Raw response: {content[:500]}")
            raise Exception("OpenAI returned invalid JSON")
        
        except Exception as e:
            logger.error(f"OpenAI API Error: {e}", exc_info=True)
            raise

    def _build_section_example_json(
        self,
        section_names: List[str],
        source_groups: List[List[str]]
    ) -> str:
        """Build a JSON example that mirrors the requested section names."""

        examples = []
        safe_section_names = section_names[:2] if section_names else []
        while len(safe_section_names) < 2:
            safe_section_names.append(f"Section {len(safe_section_names) + 1}")

        for index, section_name in enumerate(safe_section_names[:2]):
            source_list = source_groups[index] if index < len(source_groups) else []
            examples.append({
                "section_name": section_name,
                "content": "Detailed content here..." if index == 0 else "Detailed narrative...",
                "confidence": 0.95 if index == 0 else 0.90,
                "sources": source_list
            })

        return json.dumps({"sections": examples}, indent=2)

    def _post_process_sections(
        self,
        report_sections: List[DischargeReportSection],
        patient_record: PatientRecord,
        clinical_documentation: ClinicalDocumentation,
        report_template: Optional[ReportTemplate]
    ) -> List[DischargeReportSection]:
        """Apply safety checks after generation."""

        sections = self._ensure_allergies_present(
            report_sections,
            patient_record,
            report_template
        )

        validated_sections = []
        for section in sections:
            validated_sections.append(
                self._flag_untraceable_clinical_terms(
                    section,
                    patient_record,
                    clinical_documentation
                )
            )

        return validated_sections

    def _ensure_allergies_present(
        self,
        report_sections: List[DischargeReportSection],
        patient_record: PatientRecord,
        report_template: Optional[ReportTemplate]
    ) -> List[DischargeReportSection]:
        """Ensure documented allergies appear in the generated report."""

        if not patient_record.allergies:
            return report_sections

        allergy_text = ", ".join(patient_record.allergies)
        if any(allergy.lower() in self._assemble_section_text(report_sections).lower() for allergy in patient_record.allergies):
            return report_sections

        preferred_names = ["Allergies", "Discharge Diagnosis"]
        if report_template:
            template_section_names = {section.lower(): section for section in report_template.sections}
            for preferred_name in preferred_names:
                if preferred_name.lower() in template_section_names:
                    target_name = template_section_names[preferred_name.lower()]
                    return self._append_text_to_section(
                        report_sections,
                        target_name,
                        f"Known allergies: {allergy_text}."
                    )

        if report_sections:
            return self._append_text_to_section(
                report_sections,
                report_sections[0].section_name,
                f"Known allergies: {allergy_text}."
            )

        return [
            DischargeReportSection(
                section_name="Allergies",
                content=f"Known allergies: {allergy_text}.",
                confidence=1.0,
                sources=["patient_record"]
            )
        ]

    def _append_text_to_section(
        self,
        report_sections: List[DischargeReportSection],
        target_section_name: str,
        extra_text: str
    ) -> List[DischargeReportSection]:
        """Append text to a section, creating a copy of the section list."""

        updated_sections = []
        appended = False
        for section in report_sections:
            if not appended and section.section_name == target_section_name:
                content = section.content.rstrip()
                if extra_text.lower() not in content.lower():
                    content = f"{content}\n\n{extra_text}" if content else extra_text
                updated_sections.append(
                    DischargeReportSection(
                        section_name=section.section_name,
                        content=content,
                        confidence=section.confidence,
                        sources=section.sources,
                    )
                )
                appended = True
            else:
                updated_sections.append(section)

        if not appended:
            updated_sections.append(
                DischargeReportSection(
                    section_name=target_section_name,
                    content=extra_text,
                    confidence=0.95,
                    sources=["patient_record"]
                )
            )

        return updated_sections

    def _assemble_section_text(self, sections: List[DischargeReportSection]) -> str:
        """Flatten section contents for a presence check."""

        return "\n".join(section.content for section in sections)

    def _build_source_text_map(self, docs: ClinicalDocumentation) -> Dict[str, str]:
        """Build a lookup of source document text by source key."""

        return {
            "admission_notes": docs.admission_notes or "",
            "progress_notes": "\n".join(docs.progress_notes),
            "procedures": self._format_procedures(docs.procedures_performed),
            "procedures_performed": self._format_procedures(docs.procedures_performed),
            "lab_results": json.dumps(docs.lab_results, indent=2),
            "imaging_results": self._format_imaging(docs.imaging_results),
            "consultation_notes": "\n".join(docs.consultation_notes),
            "prior_discharge_summaries": "\n".join(docs.prior_discharge_summaries),
        }

    def _flag_untraceable_clinical_terms(
        self,
        section: DischargeReportSection,
        patient_record: PatientRecord,
        docs: ClinicalDocumentation
    ) -> DischargeReportSection:
        """Lower confidence and add a reviewer note when a section contains untraceable terms."""

        source_text_map = self._build_source_text_map(docs)
        source_text_map.update({
            "primary_diagnosis": patient_record.primary_diagnosis or "",
            "secondary_diagnoses": "\n".join(patient_record.secondary_diagnoses),
            "allergies": "\n".join(patient_record.allergies),
            "medications_on_admission": self._format_medications(patient_record.medications_on_admission),
        })
        allowed_sources = section.sources or list(source_text_map.keys())
        source_text = "\n".join(
            source_text_map.get(source_key, "")
            for source_key in allowed_sources
        ).strip()

        source_terms = self._extract_clinical_terms(source_text)
        candidate_terms = self._extract_clinical_terms(section.content)
        discrepancy_notes, untraceable_terms = self._detect_clinical_issues(
            candidate_terms=candidate_terms,
            source_terms=source_terms,
            source_text=source_text,
        )

        if not discrepancy_notes and not untraceable_terms:
            return section

        note_parts = []
        if discrepancy_notes:
            note_parts.extend(discrepancy_notes)
        if untraceable_terms:
            note_parts.append(
                "unverified clinical terms detected: "
                + ", ".join(sorted(set(untraceable_terms)))
            )

        reviewer_note = "Reviewer warning: " + "; ".join(note_parts) + "."
        content = section.content.rstrip()
        if reviewer_note.lower() not in content.lower():
            content = f"{content}\n\n{reviewer_note}" if content else reviewer_note

        penalty_terms = len(set(untraceable_terms)) + len(set(discrepancy_notes))
        lowered_confidence = max(0.0, round(section.confidence - (0.10 * penalty_terms), 2))

        return DischargeReportSection(
            section_name=section.section_name,
            content=content,
            confidence=lowered_confidence,
            sources=section.sources
        )

    def _detect_clinical_issues(
        self,
        candidate_terms: List[str],
        source_terms: List[str],
        source_text: str
    ) -> Tuple[List[str], List[str]]:
        """Detect specific abbreviation mismatches and generic untraceable terms."""

        specific_discrepancies = []
        untraceable = []

        source_term_set = {term.upper() for term in source_terms}

        for candidate in candidate_terms:
            discrepancy_note = self._detect_abbreviation_discrepancy(candidate, source_term_set)
            if discrepancy_note:
                specific_discrepancies.append(discrepancy_note)
                continue

            if self._term_matches_source(candidate, source_terms, source_text):
                continue

            untraceable.append(candidate)

        return specific_discrepancies, untraceable

    def _extract_clinical_terms(self, text: str) -> List[str]:
        """Extract likely clinical abbreviations or procedure names from text."""

        if not text:
            return []

        terms = set()

        acronym_pattern = r"(?<![A-Za-z0-9])([A-Z]{2,}(?:[-/][A-Z0-9]+)*)(?![A-Za-z0-9])"
        for match in re.findall(acronym_pattern, text):
            terms.add(match.upper())

        procedure_keywords = [
            "echocardiogram",
            "echocardiography",
            "angiography",
            "catheterization",
            "catheterisation",
            "stent",
            "ultrasound",
            "endoscopy",
            "biopsy",
            "x-ray",
            "xray",
            "ct",
            "mri",
            "ecg",
            "ekg",
            "pci",
            "stemi",
            "tee",
            "tte",
        ]
        for keyword in procedure_keywords:
            if self._contains_whole_term(text, keyword):
                terms.add(keyword.upper())

        # Treat standalone ST as suspicious only when it is actually used as a claim,
        # not when it is part of STEMI / ST-elevation wording.
        if self._contains_whole_term(text, "ST"):
            if not self._contains_whole_term(text, "STEMI") and not self._contains_whole_term(text, "ST-ELEVATION") and not self._contains_whole_term(text, "ST ELEVATION"):
                terms.add("ST")

        return sorted(terms)

    def _contains_whole_term(self, text: str, term: str) -> bool:
        """Check whether a term appears as a standalone token or phrase."""

        if not text or not term:
            return False

        pattern = rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])"
        return re.search(pattern, text, flags=re.IGNORECASE) is not None

    def _detect_abbreviation_discrepancy(
        self,
        candidate: str,
        source_terms: set
    ) -> Optional[str]:
        """Detect common abbreviation swaps such as TTE vs TEE."""

        pair_map = {
            "tee": "tte",
            "tte": "tee",
            "ekg": "ecg",
            "ecg": "ekg",
        }

        normalized_candidate = candidate.lower()
        counterpart = pair_map.get(normalized_candidate)
        if not counterpart:
            return None

        if counterpart.upper() in source_terms and normalized_candidate.upper() not in source_terms:
            return f"source says {counterpart.upper()}, generated text says {normalized_candidate.upper()}"

        return None

    def _term_matches_source(
        self,
        candidate: str,
        source_terms: List[str],
        source_text: str
    ) -> bool:
        """Check whether a candidate term is supported by source text."""

        normalized_candidate = candidate.lower()
        if self._contains_whole_term(source_text, normalized_candidate):
            return True

        normalized_sources = [term.lower() for term in source_terms]
        if normalized_candidate in normalized_sources:
            return True

        if self._matches_known_clinical_equivalence(normalized_candidate, normalized_sources, source_text):
            return True

        # Avoid over-permissive matching for short abbreviations like TTE/TEE.
        if len(normalized_candidate) <= 4:
            return False

        for source_term in normalized_sources:
            if len(source_term) <= 4:
                continue
            if SequenceMatcher(None, normalized_candidate, source_term).ratio() >= 0.88:
                return True

        return False

    def _matches_known_clinical_equivalence(
        self,
        normalized_candidate: str,
        normalized_sources: List[str],
        source_text: str
    ) -> bool:
        """Allow verified abbreviation-expansion pairs and expected clinical variants."""

        equivalence_groups = {
            "tte": [
                "transthoracic echocardiogram",
                "transthoracic echocardiography",
                "echocardiogram",
                "echocardiography",
                "echo",
            ],
            "echocardiogram": [
                "tte",
                "transthoracic echocardiogram",
                "transthoracic echocardiography",
                "echocardiography",
                "echo",
            ],
            "echocardiography": [
                "tte",
                "transthoracic echocardiogram",
                "transthoracic echocardiography",
                "echocardiogram",
                "echo",
            ],
            "pci": [
                "percutaneous coronary intervention",
            ],
            "stemi": [
                "st-elevation myocardial infarction",
                "st elevation myocardial infarction",
            ],
            "st": [
                "stemi",
                "st-elevation myocardial infarction",
                "st elevation myocardial infarction",
            ],
            "procedure": [
                "procedure performed",
                "procedures performed",
                "performed procedure",
            ],
            "intervention": [
                "procedure",
                "procedures",
                "performed",
            ],
            "imaging": [
                "x-ray",
                "xray",
                "ct",
                "mri",
                "ultrasound",
            ],
        }

        aliases = equivalence_groups.get(normalized_candidate, [])
        if not aliases:
            return False

        for alias in aliases:
            if self._contains_whole_term(source_text, alias):
                return True
            if alias.lower() in normalized_sources:
                return True

        return False
    
    # =========================================================================
    # Helper Methods
    # =========================================================================
    
    def _format_list(self, items: List[str]) -> str:
        """Format list for prompt."""
        if not items:
            return "- None documented"
        return "\n".join([f"- {item}" for item in items])
    
    def _format_medications(self, meds: List[Dict[str, str]]) -> str:
        """Format medications."""
        if not meds:
            return "- None documented"
        
        formatted = []
        for med in meds:
            med_str = f"- {med.get('name', 'Unknown')}"
            if 'dose' in med:
                med_str += f" {med['dose']}"
            if 'frequency' in med:
                med_str += f" {med['frequency']}"
            formatted.append(med_str)
        
        return "\n".join(formatted)
    
    def _format_progress_notes(self, notes: List[str]) -> str:
        """Format progress notes."""
        if not notes:
            return "No progress notes provided"
        
        formatted = []
        for i, note in enumerate(notes, 1):
            formatted.append(f"**Day {i}:**\n{note}\n")
        
        return "\n".join(formatted)
    
    def _format_procedures(self, procedures: List[Dict[str, str]]) -> str:
        """Format procedures."""
        if not procedures:
            return "- No procedures documented"
        
        formatted = []
        for proc in procedures:
            proc_str = f"- {proc.get('name', 'Unknown procedure')}"
            if 'date' in proc:
                proc_str += f" (Date: {proc['date']})"
            if 'result' in proc:
                proc_str += f"\n  Result: {proc['result']}"
            formatted.append(proc_str)
        
        return "\n".join(formatted)
    
    def _format_imaging(self, imaging: List[Dict[str, str]]) -> str:
        """Format imaging results."""
        if not imaging:
            return "- No imaging documented"
        
        formatted = []
        for img in imaging:
            img_str = f"- {img.get('study', 'Unknown study')}"
            if 'findings' in img:
                img_str += f"\n  Findings: {img['findings']}"
            formatted.append(img_str)
        
        return "\n".join(formatted)
    
    def _assemble_full_report(
        self,
        sections: List[DischargeReportSection],
        patient: PatientRecord
    ) -> str:
        """Assemble full report text from sections."""
        
        report = f"""DISCHARGE SUMMARY

Patient ID: {patient.patient_id}
Age: {patient.age} years
Gender: {patient.gender}
Admission Date: {patient.admission_date}
Discharge Date: {patient.discharge_date or "Pending"}

Primary Diagnosis: {patient.primary_diagnosis}

{'='*80}

"""
        
        for section in sections:
            report += f"{section.section_name.upper()}\n"
            report += f"{'-'*80}\n"
            report += f"{section.content}\n\n"
        
        report += f"\n{'='*80}\n"
        report += "⚠️ DRAFT - Requires Physician Review and Approval\n"
        report += f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        
        return report
    
    def _calculate_confidence(self, sections: List[DischargeReportSection]) -> float:
        """Calculate overall confidence score."""
        if not sections:
            return 0.0
        
        return sum(s.confidence for s in sections) / len(sections)
    
    def _create_fallback_report(self, error: str) -> List[DischargeReportSection]:
        """Create fallback report on error."""
        return [
            DischargeReportSection(
                section_name="Error",
                content=f"Unable to generate discharge report: {error}",
                confidence=0.0,
                sources=[]
            )
        ]


# Global instance
discharge_report_generator = DischargeReportGenerator()
