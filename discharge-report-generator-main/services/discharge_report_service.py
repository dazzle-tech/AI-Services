"""
Discharge Report Generation Service using OpenAI GPT-4
Generates discharge summaries from clinical documentation.
"""

import os
import json
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime
from openai import OpenAI  # Import the OpenAI client class

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
            print("⚠️  Warning: OPENAI_API_KEY not configured for discharge reports")
        
        self.model = config.OPENAI_MODEL
        self.temperature = 0.2  # Slightly higher for more natural medical writing
        
    def initialize(self):
        """Initialize the service."""
        if not self.initialized:
            if self.openai_api_key:
                # Initialize OpenAI client (NEW API - v1.0+)
                self.client = OpenAI(api_key=self.openai_api_key)
            self.initialized = True
            print("✅ Discharge Report Generator initialized")
    
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
            print(f"❌ OpenAI API Error: {e}")
            report_sections = self._create_fallback_report(str(e))
        
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

{{
  "sections": [
    {{
      "section_name": "Chief Complaint",
      "content": "Detailed content here...",
      "confidence": 0.95,
      "sources": ["admission_notes", "progress_notes"]
    }},
    {{
      "section_name": "Hospital Course",
      "content": "Detailed narrative...",
      "confidence": 0.90,
      "sources": ["progress_notes", "procedures"]
    }}
  ]
}}

# IMPORTANT GUIDELINES

- Write in past tense for completed care
- Use standard medical abbreviations appropriately
- Include quantitative data (lab values, vitals) when relevant
- Maintain professional, objective tone
- If information is missing or unclear, note "Information not available in provided documentation"
- Confidence score should reflect data quality (0.0-1.0)

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

{{
  "sections": [
    {{
      "section_name": "Chief Complaint",
      "content": "...",
      "confidence": 0.95,
      "sources": ["admission_notes"]
    }}
  ]
}}

# GUIDELINES

- Professional medical language
- Chronological narrative for hospital course
- Include specific clinical details and values
- Clear discharge instructions
- Confidence based on documentation quality

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
                response_format={"type": "json_object"}
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
                    print(f"⚠️  Error parsing section: {e}")
                    continue
            
            return sections
            
        except json.JSONDecodeError as e:
            print(f"❌ JSON Parse Error: {e}")
            print(f"   Raw response: {content[:500]}")
            raise Exception("OpenAI returned invalid JSON")
        
        except Exception as e:
            print(f"❌ OpenAI API Error: {e}")
            raise
    
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