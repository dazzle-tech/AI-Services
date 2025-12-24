"""
OpenAI-Powered Medical Guideline Validation Service
Uses GPT-4 to intelligently analyze orders against clinical guidelines.
"""

import os
import json
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime
from openai import OpenAI  # Import the OpenAI client class

from models.schemas import (
    MedicalNote, 
    SeverityLevel, 
    GuidelineCheckResponse
)
from services.guidelines_service import guidelines_service


class OpenAIGuidelineValidator:
    """
    AI-powered guideline validator using OpenAI API.
    Provides intelligent, context-aware clinical decision support.
    """
    
    def __init__(self):
        self.initialized = False
        self.openai_api_key = None
        self.client = None  # OpenAI client instance
        
        # Model configuration
        self.model = "gpt-4o"  # or "gpt-4-turbo" or "gpt-4"
        self.temperature = 0.1  # Low temperature for consistent medical reasoning
        
    def initialize(self):
        """Initialize the validator."""
        if not self.initialized:
            # Load API key from environment
            self.openai_api_key = os.environ.get("OPENAI_API_KEY")
            
            if not self.openai_api_key:
                print("⚠️  ERROR: OPENAI_API_KEY not found in environment variables")
                print("   Make sure your .env file contains: OPENAI_API_KEY=sk-...")
                return
            
            # Initialize OpenAI client (NEW API - v1.0+)
            self.client = OpenAI(api_key=self.openai_api_key)
            
            # Initialize guidelines service
            guidelines_service.initialize()
            
            self.initialized = True
            print("✅ OpenAI Guideline Validator initialized")
            print(f"   Using model: {self.model}")
            print(f"   API Key: {self.openai_api_key[:15]}...{self.openai_api_key[-4:]}")
    
    # =========================================================================
    # Main Validation Method (OpenAI-Powered)
    # =========================================================================
    
    async def validate_orders(
        self,
        patient_id: str,
        active_orders: Dict[str, List[Dict[str, Any]]],
        clinical_context: Dict[str, Any],
        patient_record: Dict[str, Any],
        specialty: Optional[str] = None
    ) -> GuidelineCheckResponse:
        """
        AI-powered validation using OpenAI API.
        
        Process:
        1. Retrieve relevant guidelines using RAG
        2. Build comprehensive prompt with patient context
        3. Send to OpenAI for intelligent analysis
        4. Parse structured JSON response
        5. Return formatted validation results
        """
        
        if not self.initialized:
            self.initialize()
        
        # Extract diagnosis and department
        diagnosis = clinical_context.get("working_diagnosis", "Unknown")
        department = patient_record.get("department", specialty or "General")
        
        # Step 1: Retrieve relevant guidelines using RAG
        guidelines_text, guideline_sources = self._retrieve_relevant_guidelines(
            diagnosis=diagnosis,
            department=department
        )
        
        # Step 2: Build comprehensive prompt
        prompt = self._build_validation_prompt(
            patient_id=patient_id,
            active_orders=active_orders,
            clinical_context=clinical_context,
            patient_record=patient_record,
            guidelines_text=guidelines_text,
            diagnosis=diagnosis
        )
        
        # Step 3: Call OpenAI API
        try:
            medical_notes = await self._call_openai_for_validation(prompt)
        except Exception as e:
            print(f"❌ OpenAI API Error: {e}")
            # Fallback to basic validation
            medical_notes = self._create_fallback_note(str(e))
        
        # Step 4: Calculate summary statistics
        severity_counts = self._calculate_severity_counts(medical_notes)
        overall_severity = self._determine_overall_severity(medical_notes)
        
        # Step 5: Generate summary
        summary = self._generate_summary(medical_notes, diagnosis, severity_counts)
        
        # Safety disclaimer
        disclaimer = (
            "⚠️ IMPORTANT: This is an AI-powered clinical decision support tool. "
            "All recommendations must be reviewed by a qualified healthcare professional "
            "before implementation. Do not use for autonomous decision-making. "
            "AI systems can make errors - always verify recommendations against current guidelines."
        )
        
        return GuidelineCheckResponse(
            patient_id=patient_id,
            check_timestamp=datetime.now().isoformat(),
            overall_severity=overall_severity,
            summary=summary,
            medical_notes=medical_notes,
            total_issues_found=len(medical_notes),
            critical_count=severity_counts["critical"],
            high_count=severity_counts["high"],
            moderate_count=severity_counts["moderate"],
            routine_count=severity_counts["routine"],
            safety_disclaimer=disclaimer,
            requires_urgent_review=(severity_counts["critical"] > 0 or severity_counts["high"] > 0),
            guidelines_consulted=guideline_sources
        )
    
    # =========================================================================
    # RAG: Retrieve Relevant Guidelines
    # =========================================================================
    
    def _retrieve_relevant_guidelines(
        self,
        diagnosis: str,
        department: str
    ) -> Tuple[str, List[str]]:
        """
        Use RAG to retrieve relevant clinical guidelines for the diagnosis.
        """
        
        # Build search query
        query = f"{diagnosis} treatment protocol initial management guidelines"
        
        # Search guidelines
        guidelines = guidelines_service.search_guidelines(
            query=query,
            k=5,  # Get top 5 most relevant sections
            filter_specialty=department.lower() if department else None
        )
        
        if not guidelines:
            return (
                f"No specific guidelines found for {diagnosis}. "
                "Please ensure orders follow institutional protocols.",
                ["Institutional Protocols"]
            )
        
        # Extract guideline content and sources
        guideline_text = "\n\n---\n\n".join([
            f"**Source: {g.get('source', 'Unknown')}** (Page {g.get('page', 'N/A')})\n\n{g['content']}"
            for g in guidelines
        ])
        
        guideline_sources = list(set([g.get("source", "Unknown") for g in guidelines]))
        
        return guideline_text, guideline_sources
    
    # =========================================================================
    # Prompt Engineering: Build OpenAI Prompt
    # =========================================================================
    
    def _build_validation_prompt(
        self,
        patient_id: str,
        active_orders: Dict[str, List[Dict[str, Any]]],
        clinical_context: Dict[str, Any],
        patient_record: Dict[str, Any],
        guidelines_text: str,
        diagnosis: str
    ) -> str:
        """
        Build comprehensive prompt for OpenAI API.
        """
        
        prompt = f"""You are an expert clinical decision support AI analyzing active orders against evidence-based medical guidelines.

# PATIENT INFORMATION

**Patient ID:** {patient_id}
**Age:** {patient_record.get('age', 'Unknown')} years
**Gender:** {patient_record.get('gender', 'Unknown')}
**Weight:** {patient_record.get('weight_kg', 'Unknown')} kg

**Diagnosis:** {diagnosis}
**Department:** {patient_record.get('department', 'Unknown')}

**Allergies:** {', '.join(patient_record.get('allergies', ['None documented']))}

**Comorbidities:**
{self._format_list(patient_record.get('comorbidities', ['None documented']))}

**Vital Signs:**
{json.dumps(patient_record.get('vitals', {}), indent=2)}

**Recent Labs:**
{json.dumps(patient_record.get('recent_labs', {}), indent=2)}

# CLINICAL CONTEXT

**Presentation:** {clinical_context.get('presentation', 'Not documented')}

**History:** {clinical_context.get('history', 'Not documented')}

**Physical Exam:** {clinical_context.get('physical_exam', 'Not documented')}

**Working Diagnosis:** {clinical_context.get('working_diagnosis', diagnosis)}

**Care Plan:** {clinical_context.get('care_plan', 'Not documented')}

# ACTIVE ORDERS

## Medications:
{self._format_orders(active_orders.get('medications', []))}

## Procedures:
{self._format_orders(active_orders.get('procedures', []))}

## Laboratory Tests:
{self._format_orders(active_orders.get('labs', []))}

## Imaging:
{self._format_orders(active_orders.get('imaging', []))}

# RELEVANT CLINICAL GUIDELINES

{guidelines_text}

---

# YOUR TASK

Analyze the active orders against the patient's clinical context and the provided guidelines. Identify:

1. **Contraindications** - Orders that conflict with allergies, comorbidities, or lab values
2. **Missing Components** - Required elements of guideline-based care bundles that are absent
3. **Timing Issues** - Time-sensitive interventions that may not meet guideline targets
4. **Dosing Concerns** - Medications requiring adjustment for renal function, age, or weight
5. **Safety Risks** - Any other patient safety concerns

For EACH issue identified, you MUST provide:
- Clear description of what's wrong or missing
- Clinical reasoning based on guidelines (why it matters)
- Severity level: "critical", "high", "moderate", "low", or "routine"
- Specific, actionable recommendations
- List of affected order IDs (if applicable)
- Guideline reference
- Whether human review is required (true/false)

# OUTPUT FORMAT

Respond with ONLY a valid JSON object with an "issues" array. Each element must follow this exact structure:

{{
  "issues": [
    {{
      "issue": "Clear description of the problem",
      "reasoning": "Why this matters based on guidelines and patient context",
      "affected_orders": ["order_id_1", "order_id_2"],
      "severity": "critical|high|moderate|low|routine",
      "recommendations": [
        "Specific action 1",
        "Specific action 2"
      ],
      "guideline_reference": "Name of guideline or protocol",
      "requires_human_review": true|false
    }}
  ]
}}

# SEVERITY DEFINITIONS

- **critical**: Immediate life-threatening concern requiring immediate action
- **high**: Significant patient safety risk requiring urgent attention (within 1 hour)
- **moderate**: Important issue requiring same-day attention
- **low**: Minor concern or optimization opportunity
- **routine**: Documentation or process improvement

# IMPORTANT RULES

1. If NO issues are found, return: {{"issues": []}}
2. Be specific - reference exact guidelines, lab values, and medication names
3. Prioritize patient safety over guideline adherence
4. Consider the full clinical context, not just isolated data points
5. If uncertain about severity, mark requires_human_review as true
6. Focus on actionable, implementable recommendations

Respond with JSON only, no other text:"""
        
        return prompt
    
    # =========================================================================
    # OpenAI API Call (FIXED FOR v1.0+)
    # =========================================================================
    
    async def _call_openai_for_validation(
        self,
        prompt: str
    ) -> List[MedicalNote]:
        """
        Call OpenAI API and parse response into MedicalNote objects.
        """
        
        if not self.client:
            raise Exception("OpenAI client not initialized")
        
        try:
            # Call OpenAI API using the new client
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert clinical decision support system. You analyze medical orders against guidelines and return structured JSON responses."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=self.temperature,
                response_format={"type": "json_object"}  # Ensure JSON response
            )
            
            # Extract response
            content = response.choices[0].message.content
            
            # Parse JSON
            response_data = json.loads(content)
            
            # Extract issues array
            if isinstance(response_data, dict):
                issues = response_data.get("issues", [])
            elif isinstance(response_data, list):
                issues = response_data
            else:
                issues = []
            
            # Convert to MedicalNote objects
            medical_notes = []
            for issue in issues:
                try:
                    note = MedicalNote(
                        issue=issue.get("issue", "Issue not specified"),
                        reasoning=issue.get("reasoning", "Reasoning not provided"),
                        affected_orders=issue.get("affected_orders", []),
                        severity=SeverityLevel(issue.get("severity", "moderate")),
                        recommendations=issue.get("recommendations", []),
                        guideline_reference=issue.get("guideline_reference"),
                        requires_human_review=issue.get("requires_human_review", False)
                    )
                    medical_notes.append(note)
                except Exception as e:
                    print(f"⚠️  Error parsing note: {e}")
                    print(f"   Issue data: {issue}")
                    continue
            
            return medical_notes
            
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
        """Format a list for the prompt."""
        if not items:
            return "- None documented"
        return "\n".join([f"- {item}" for item in items])
    
    def _format_orders(self, orders: List[Dict[str, Any]]) -> str:
        """Format orders for the prompt."""
        if not orders:
            return "- None ordered"
        
        formatted = []
        for order in orders:
            order_str = f"- **Order ID: {order.get('order_id', 'N/A')}**\n"
            
            # Include all relevant fields
            for key, value in order.items():
                if key != 'order_id':
                    order_str += f"  - {key}: {value}\n"
            
            formatted.append(order_str)
        
        return "\n".join(formatted)
    
    def _create_fallback_note(self, error: str) -> List[MedicalNote]:
        """Create a fallback note when OpenAI fails."""
        return [
            MedicalNote(
                issue="AI validation service unavailable",
                reasoning=f"Unable to perform AI-powered validation: {error}",
                affected_orders=[],
                severity=SeverityLevel.LOW,
                recommendations=[
                    "Manually review orders against institutional protocols",
                    "Contact clinical pharmacist for medication review",
                    "Consult relevant specialty guidelines"
                ],
                guideline_reference="Manual Review Required",
                requires_human_review=True
            )
        ]
    
    def _calculate_severity_counts(self, notes: List[MedicalNote]) -> Dict[str, int]:
        """Calculate count of each severity level."""
        counts = {
            "critical": 0,
            "high": 0,
            "urgent": 0,
            "moderate": 0,
            "low": 0,
            "routine": 0
        }
        
        for note in notes:
            severity = note.severity.value
            counts[severity] = counts.get(severity, 0) + 1
        
        return counts
    
    def _determine_overall_severity(self, notes: List[MedicalNote]) -> SeverityLevel:
        """Determine overall severity from all notes."""
        if not notes:
            return SeverityLevel.ROUTINE
        
        severities = [note.severity for note in notes]
        
        if SeverityLevel.CRITICAL in severities:
            return SeverityLevel.CRITICAL
        elif SeverityLevel.HIGH in severities or SeverityLevel.URGENT in severities:
            return SeverityLevel.HIGH
        elif SeverityLevel.MODERATE in severities:
            return SeverityLevel.MODERATE
        else:
            return SeverityLevel.LOW
    
    def _generate_summary(
        self,
        notes: List[MedicalNote],
        diagnosis: str,
        severity_counts: Dict[str, int]
    ) -> str:
        """Generate a human-readable summary of findings."""
        if not notes:
            return f"✅ AI analysis complete: All orders for {diagnosis} appear to align with clinical guidelines. No significant issues detected."
        
        total = len(notes)
        critical = severity_counts["critical"]
        high = severity_counts["high"]
        
        summary = f"AI-powered guideline check for {diagnosis}: Found {total} issue(s). "
        
        if critical > 0:
            summary += f"🚨 {critical} CRITICAL issue(s) requiring immediate attention. "
        
        if high > 0:
            summary += f"⚠️ {high} HIGH priority issue(s). "
        
        summary += "Please review AI-generated recommendations below."
        
        return summary


# Global instance
openai_guideline_validator = OpenAIGuidelineValidator()