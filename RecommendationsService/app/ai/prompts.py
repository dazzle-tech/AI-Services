"""Prompt templates for clinical recommendations generation."""
from typing import Dict, Any, List, Optional
from app.models.schemas import RecommendationType


def get_system_prompt() -> str:
    """System prompt optimized for GPT-4o clinical recommendations."""
    return """You are an expert clinical decision support AI specialized in generating evidence-based clinical recommendations.

Your task is to analyze patient context and provide comprehensive, actionable clinical recommendations that:
- Are evidence-based and clinically appropriate
- Consider patient-specific factors (age, comorbidities, allergies, medications)
- Prioritize patient safety and clinical outcomes
- Provide clear, actionable guidance for healthcare providers
- Include appropriate monitoring and follow-up considerations

CRITICAL REQUIREMENTS:
1. EVIDENCE-BASED: Base recommendations on current clinical guidelines and best practices
2. PATIENT-SPECIFIC: Tailor recommendations to the individual patient's context
3. SAFETY-FIRST: Always consider contraindications, allergies, and drug interactions
4. ACTIONABLE: Provide specific, implementable recommendations with clear steps
5. PRIORITIZED: Assign appropriate priority levels (critical, high, moderate, low, routine)
6. COMPREHENSIVE: Consider medication, diagnostic, treatment, monitoring, and lifestyle aspects

OUTPUT FORMAT:
- Return ONLY valid JSON with a "recommendations" array
- Each recommendation must include: type, title, description, rationale, priority, actionable_steps
- Include summary of all recommendations
- Provide priority breakdown"""


def format_patient_context(patient_context: Dict[str, Any]) -> str:
    """Format patient context into structured text for the prompt."""
    parts = []
    
    parts.append(f"**Patient Demographics:**")
    parts.append(f"- Age: {patient_context.get('age', 'N/A')}")
    parts.append(f"- Gender: {patient_context.get('gender', 'N/A')}")
    
    parts.append(f"\n**Clinical Information:**")
    parts.append(f"- Diagnosis: {patient_context.get('diagnosis', 'N/A')}")
    
    if patient_context.get('symptoms'):
        parts.append(f"- Symptoms: {', '.join(patient_context['symptoms'])}")
    
    if patient_context.get('medications'):
        parts.append(f"- Current Medications: {', '.join(patient_context['medications'])}")
    
    if patient_context.get('allergies'):
        parts.append(f"- Allergies: {', '.join(patient_context['allergies'])}")
    
    if patient_context.get('comorbidities'):
        parts.append(f"- Comorbidities: {', '.join(patient_context['comorbidities'])}")
    
    if patient_context.get('vitals'):
        vitals = patient_context['vitals']
        vitals_text = ", ".join([f"{k}: {v}" for k, v in vitals.items()])
        parts.append(f"- Vital Signs: {vitals_text}")
    
    if patient_context.get('lab_results'):
        import json
        parts.append(f"- Lab Results: {json.dumps(patient_context['lab_results'], indent=2)}")
    
    if patient_context.get('surgeries'):
        surgery_parts = [
            f"{s['name']} ({s['status']})" for s in patient_context['surgeries']
        ]
        parts.append(f"- Surgeries: {', '.join(surgery_parts)}")
    
    if patient_context.get('clinical_notes'):
        parts.append(f"\n**Additional Clinical Notes:**")
        parts.append(patient_context['clinical_notes'])
    
    return "\n".join(parts)


def get_user_prompt(
    patient_context: Dict[str, Any],
    recommendation_types: List[str],
    focus_areas: Optional[List[str]] = None
) -> str:
    """User prompt containing formatted patient context and request."""
    context_text = format_patient_context(patient_context)
    
    focus_text = ""
    if focus_areas:
        focus_text = f"\n**Focus Areas:** {', '.join(focus_areas)}\n"
    
    return f"""Analyze the following patient context and generate comprehensive medical recommendations.

{context_text}
{focus_text}

Generate evidence-based medical recommendations that:
1. Are appropriate for this patient's age, gender, diagnosis, and clinical context
2. Consider current medications, allergies, and comorbidities
3. Include specific, actionable steps
4. Assign appropriate priority levels based on clinical urgency
5. Include rationale and evidence considerations
6. Note any contraindications or precautions

For each recommendation, provide:
- Type: Always use "medical" for all recommendations
- Clear title
- Detailed description
- Clinical rationale
- Priority level (critical, high, moderate, low, or routine)
- Specific actionable steps
- Evidence level (if applicable)
- Contraindications to consider
- Monitoring requirements (if needed)
- Follow-up recommendations (if applicable)

Return your response as JSON with this structure:
{{
  "recommendations": [
    {{
      "recommendation_id": "rec_1",
      "type": "medical",
      "title": "Short title",
      "description": "Detailed recommendation",
      "rationale": "Why this is recommended",
      "priority": "high",
      "actionable_steps": ["Step 1", "Step 2"],
      "evidence_level": "Strong",
      "contraindications": [],
      "monitoring_requirements": "Monitor X, Y",
      "follow_up": "Follow-up in Z weeks"
    }}
  ],
  "summary": "Brief summary of all recommendations",
  "priority_breakdown": {{"critical": 0, "high": 2, "moderate": 1, "low": 0, "routine": 0}}
}}

Generate the medical recommendations now:"""


def build_recommendations_prompt(
    patient_context: Dict[str, Any],
    recommendation_types: List[str],
    focus_areas: Optional[List[str]] = None
) -> List[Dict[str, str]]:
    """Build complete prompt structure for OpenAI API."""
    return [
        {
            "role": "system",
            "content": get_system_prompt()
        },
        {
            "role": "user",
            "content": get_user_prompt(patient_context, recommendation_types, focus_areas)
        }
    ]


def build_specialty_prompt(
    specialty: str,
    patient_context: Dict[str, Any],
    complaint: Optional[str] = None
) -> List[Dict[str, str]]:
    """Build prompt for specialty-based consultation: set of actions considering full patient context."""
    specialty_context = ""
    if patient_context and any(v for k, v in patient_context.items() if v is not None and v != [] and v != {}):
        specialty_context = f"\n**FULL PATIENT CONTEXT (consider all of this):**\n{format_patient_context(patient_context)}\n"
    
    complaint_text = f"\n**Chief Complaint:** {complaint}\n" if complaint else ""
    
    system_prompt = f"""You are an expert {specialty} specialist. Your task is to produce a clear, ordered SET OF ACTIONS for this consultation.

You MUST take into consideration the ENTIRE patient context when present:
- Demographics (age, gender)
- Diagnosis and chief complaint
- Symptoms, current medications, allergies, comorbidities
- Vital signs and lab results
- Past and scheduled surgeries
- Clinical notes

Output a structured set of actions (diagnostic, treatment, monitoring, follow-up) tailored to the patient when context is provided, or general {specialty} actions when it is not. Each action must be specific and actionable.

Return ONLY valid JSON with an "actions" array and a "summary" string."""

    user_prompt = f"""Produce a set of actions for this {specialty} consultation.
{complaint_text}{specialty_context}

Requirements:
1. Consider EVERY element of the patient context above (age, gender, diagnosis, symptoms, medications, allergies, comorbidities, vitals, lab results, surgeries, complaint). Tailor actions to this specific patient when context is provided.
2. Output an ordered set of actions: diagnostics to order, treatments to consider, monitoring steps, and follow-up. Each action should be clear and actionable.
3. Assign each action a category (diagnostic, treatment, monitoring, follow_up) and priority (high, moderate, routine) where appropriate.

Return your response as JSON with this exact structure:
{{
  "actions": [
    {{
      "title": "Short action title",
      "description": "What to do and why, considering patient context",
      "category": "diagnostic",
      "priority": "high"
    }},
    {{
      "title": "Next action title",
      "description": "What to do and why",
      "category": "treatment",
      "priority": "moderate"
    }}
  ],
  "summary": "Two to four sentence summary of the consultation plan, taking into account the full patient picture."
}}

Generate the set of actions now:"""

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]


def build_role_based_prompt(
    user_role: str,
    patient_context: Dict[str, Any],
    recommendation_types: List[str],
    complaint: Optional[str] = None,
    focus_areas: Optional[List[str]] = None
) -> List[Dict[str, str]]:
    """Build prompt for user role-based recommendations."""
    context_text = format_patient_context(patient_context)
    
    types_text = ", ".join([t.value if hasattr(t, 'value') else str(t) for t in recommendation_types])
    
    complaint_text = f"\n**Chief Complaint:** {complaint}\n" if complaint else ""
    focus_text = f"\n**Focus Areas:** {', '.join(focus_areas)}\n" if focus_areas else ""
    
    system_prompt = f"""You are an expert {user_role} specialist providing clinical recommendations from a {user_role} perspective.

Your task is to analyze patient data and provide recommendations AS A {user_role.upper()} SPECIALIST would:
- Focus on {user_role}-specific considerations
- Provide recommendations relevant to {user_role} practice
- Consider {user_role} guidelines and protocols
- Think like a {user_role} specialist evaluating this patient

Return ONLY valid JSON with recommendations array, summary, and priority_breakdown."""

    user_prompt = f"""You are a {user_role} specialist. Analyze this patient and provide recommendations from YOUR {user_role} perspective.

{context_text}
{complaint_text}
**Requested Recommendation Types:** {types_text}
{focus_text}

As a {user_role} specialist, what are your recommendations for this patient?
- What {user_role}-specific tests or procedures would you order?
- What {user_role} treatments would you consider?
- What {user_role} monitoring would you recommend?
- What are the {user_role}-specific considerations?

Provide recommendations as a {user_role} specialist would, considering:
1. {user_role}-specific diagnostic workup
2. {user_role} treatment protocols
3. {user_role} monitoring requirements
4. {user_role} referral criteria if needed

Return your response as JSON with this structure:
{{
  "recommendations": [
    {{
      "recommendation_id": "rec_1",
      "type": "medical",
      "title": "{user_role}-specific test",
      "description": "As a {user_role} specialist, I recommend...",
      "rationale": "From a {user_role} perspective...",
      "priority": "high",
      "actionable_steps": ["Step 1", "Step 2"],
      "evidence_level": "Strong",
      "contraindications": [],
      "monitoring_requirements": "{user_role}-specific monitoring",
      "follow_up": "Follow-up as {user_role} specialist"
    }}
  ],
  "summary": "Recommendations from {user_role} specialist perspective",
  "priority_breakdown": {{"critical": 0, "high": 2, "moderate": 1, "low": 0, "routine": 0}}
}}

Generate {user_role} specialist medical recommendations now:"""

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

