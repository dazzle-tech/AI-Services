"""Prompt templates for AI model interactions."""
from typing import Dict, Any, List
from app.core.constants import UserRole, SupportedLanguage


def get_system_prompt(
    user_role: UserRole,
    department: str,
    expected_fields: List[str],
    input_language: SupportedLanguage,
    output_language: SupportedLanguage,
    vitals_only: bool = False
) -> str:
    """System prompt defining safety, behavior rules, and context."""
    if vitals_only:
        # Ultra-simplified prompt for vitals-only (faster processing, prevents extraction of other fields)
        return f"""Extract ONLY vital signs (bp, hr, temp, rr, o2_sat) from clinical text.

CRITICAL: Do NOT extract any other fields (no chief_complaint, medications, diagnosis, etc.). Only vitals.

Rules:
- Extract ONLY vitals explicitly mentioned
- Set missing vitals to null
- Use path notation for flags: vitals.temp, vitals.rr, etc.
- Return valid JSON with ONLY vitals in structured_fields"""
    
    role_context = {
        UserRole.DOCTOR: "You are extracting data for a physician. All clinical fields are accessible.",
        UserRole.NURSE: "You are extracting data for a nurse. Some restricted fields (diagnosis, procedures) should not be included.",
        UserRole.ADMIN: "You are extracting data for an administrator. Only basic documentation fields are accessible."
    }
    
    return f"""You are a medical AI assistant specialized in extracting structured clinical data from free-text clinical documentation.

CONTEXT:
- User Role: {user_role.value} ({role_context.get(user_role, '')})
- Department: {department}
- Input Language: {input_language.value}
- Output Language: {output_language.value}
- Expected Output Fields: {', '.join(expected_fields)}

IMPORTANT: Only flag uncertainty for fields in the Expected Output Fields list above.
Do not create uncertainty flags for fields that were not requested (unless explicitly needed for completeness).

CRITICAL SAFETY RULES:
1. NEVER hallucinate or invent medical data (diagnoses, medications, vitals, procedures)
2. NEVER infer missing medical data - if evidence is insufficient, return null
3. If you cannot find clear evidence for a field, set it to null and add an uncertainty flag
4. Always cross-check extracted data against provided patient records
5. Flag any contradictions between user text and patient records
6. This system provides decision support ONLY - no autonomous medical decisions

EXTRACTION RULES:
- Extract only data explicitly mentioned in the user text
- Use patient record data to validate, not to fill missing fields
- Preserve exact terminology and values when possible
- For medications: extract name, dosage, frequency, route if mentioned
- For vitals: extract exact values with units if mentioned
- For diagnoses: extract only explicitly stated diagnoses
- For plan, assessment, chief_complaint, history_of_present_illness, past_medical_history, family_history, and social_history: return a single string, not a list
- For history_of_present_illness, preserve age and sex when they are part of the opening sentence
- For procedures, include only procedures that were actually performed or completed, not planned or ordered items
- For allergies, use an empty list when the text states no known allergies / NKDA

OUTPUT FORMAT:
- You MUST respond with valid JSON only
- Follow the exact schema provided
- Include all requested fields, even if null
- Add uncertainty_flags for any fields where evidence is insufficient
- Add contradictions for any mismatches with patient records
- Include source_trace for each extracted field"""




def get_user_prompt(user_text: str, patient_data: Dict[str, Any], vitals_only: bool = False) -> str:
    """User prompt containing clinical text and patient data."""
    import json
    
    patient_data_str = json.dumps(patient_data, indent=2, ensure_ascii=False)
    
    if vitals_only:
        # Ultra-simplified prompt for vitals-only extraction (faster, smaller response)
        vitals_data = patient_data.get("vitals", {})
        vitals_str = json.dumps(vitals_data, ensure_ascii=False) if vitals_data else "{}"
        return f"""TEXT: {user_text}
PATIENT VITALS: {vitals_str}

Extract ONLY vitals (bp, hr, temp, rr, o2_sat). DO NOT extract medications, diagnosis, chief_complaint, or any other fields.

Return JSON:
{{
  "structured_fields": {{
    "vitals": {{
      "bp": "value or null",
      "hr": "value or null",
      "temp": "value or null",
      "rr": "value or null",
      "o2_sat": "value or null",
      "map": "value or null",
      "measurement_site": "value or null",
      "note": "value or null"
    }}
  }},
  "uncertainty_flags": [{{"field_name": "vitals.temp", "reason": "not mentioned", "confidence": "high"}}],
  "contradictions": [{{"field_name": "vitals.bp", "user_text_value": "value", "patient_record_value": "value", "recommendation": "verify"}}],
  "source_trace": [{{"field_name": "vitals.bp", "source": "user_text", "extraction_method": "direct"}}]
}}"""
    
    return f"""CLINICAL TEXT FROM USER:
{user_text}

PATIENT RECORD DATA:
{patient_data_str}

INSTRUCTIONS:
1. Extract structured data from the clinical text above
2. Cross-check extracted values against the patient record data
3. If a value in the clinical text contradicts the patient record, flag it in contradictions
4. If evidence is insufficient for a requested field, set it to null and add an uncertainty flag
5. For each extracted field, note the source in source_trace
6. Return valid JSON only, following this schema:

{{
  "structured_fields": {{
    "chief_complaint": "string or null",
    "history_of_present_illness": "string or null",
  "diagnosis": ["string"] or null,
  "medications": [{{"name": "string", "dosage": "string", "frequency": "string", "route": "string"}}] or null,
  "vitals": {{"bp": "string", "hr": "string", "temp": "string", "rr": "string", "o2_sat": "string"}} or null,
  "procedures": ["string"] or null,
  "allergies": ["string"] or null,
  "assessment": "string or null",
  "plan": "string or null",
  "past_medical_history": "string or null",
  "family_history": "string or null",
  "social_history": "string or null",
  "review_of_systems": {{"system_name": "string"}} or null
  }},
  "uncertainty_flags": [
    {{"field_name": "string", "reason": "string", "confidence": "low|medium|high"}}
  ],
  
  CRITICAL: For uncertainty_flags.field_name, use PATH NOTATION:
  - Top-level fields: "vitals", "medications", "procedures", "chief_complaint"
  - Nested object fields: "vitals.temp", "vitals.bp", "vitals.hr", "vitals.rr", "vitals.o2_sat"
  - Array item fields: "medications[0].route", "medications[0].dosage", "medications[1].name"
  - DO NOT use bare subfield names like "temp", "route" - always include the parent path
  
  Examples:
  - Missing temperature: {{"field_name": "vitals.temp", "reason": "...", "confidence": "high"}}
  - Missing medication route: {{"field_name": "medications[0].route", "reason": "...", "confidence": "high"}}
  - Missing top-level field: {{"field_name": "procedures", "reason": "...", "confidence": "high"}}
  "contradictions": [
    {{"field_name": "string", "user_text_value": "any", "patient_record_value": "any", "recommendation": "string"}}
  ],
  "source_trace": [
    {{"field_name": "string", "source": "user_text|patient_record|inferred", "extraction_method": "string"}}
  ]
}}"""




def build_complete_prompt(
    user_text: str,
    patient_data: Dict[str, Any],
    user_role: UserRole,
    department: str,
    expected_fields: List[str],
    input_language: SupportedLanguage,
    output_language: SupportedLanguage,
    vitals_only: bool = False
) -> List[Dict[str, str]]:
    """Build complete prompt structure for OpenAI API."""
    return [
        {
            "role": "system",
            "content": get_system_prompt(
                user_role, department, expected_fields, input_language, output_language, vitals_only
            )
        },
        {"role": "user", "content": get_user_prompt(user_text, patient_data, vitals_only)}
    ]

