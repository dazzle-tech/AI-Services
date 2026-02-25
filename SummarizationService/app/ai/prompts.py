"""Prompt templates for clinical summary generation."""
import json
from typing import Dict, Any, List


def get_system_prompt() -> str:
    """System prompt optimized for GPT-4o clinical summary generation."""
    return """You are an expert medical documentation AI specialized in creating concise, coherent clinical summary paragraphs using GPT-4.

Your task is to transform structured patient data into a single, well-written clinical summary paragraph that:
- Reads naturally and professionally
- Preserves all medical terminology, abbreviations, and values exactly as provided
- Maintains clinical accuracy and completeness
- Flows logically from patient demographics through clinical findings

CRITICAL REQUIREMENTS:
1. FIDELITY: ONLY use information explicitly provided - never invent, infer, or assume additional details
2. PRECISION: Preserve exact medical abbreviations (e.g., "BID", "PRN", "STEMI"), numbers, units, and terminology
3. STRUCTURE: Create ONE coherent paragraph (typically 3-5 sentences) that flows naturally
4. LANGUAGE: Use professional medical documentation style - clear, concise, objective
5. COMPLETENESS: Include all provided information (demographics, diagnosis, symptoms, medications, allergies, vitals, etc.)

OUTPUT FORMAT:
- Return ONLY the clinical summary text - no labels, headers, or meta-commentary
- Start directly with patient description (e.g., "A 45-year-old male...")
- End with a complete sentence - no trailing fragments
- Typical length: 150-300 words depending on data provided"""


def format_patient_data(patient_data: Dict[str, Any]) -> str:
    """Format patient data into a structured text for the prompt."""
    # Use age exactly as provided (no calculation / conversion)
    raw_age = patient_data.get("Age", "N/A")
    age_text = str(raw_age) if raw_age is not None else "N/A"
    
    gender = patient_data.get("Gender", "N/A")
    diagnosis = patient_data.get("Diagnosis", "N/A")
    
    # First sentence uses the raw strings
    parts = [f"A {age_text} {gender} with {diagnosis}"]
    
    if patient_data.get("Symptoms"):
        parts.append("Symptoms: " + ", ".join(patient_data["Symptoms"]))
    if patient_data.get("Medications"):
        parts.append("Medications: " + ", ".join(patient_data["Medications"]))
    if patient_data.get("Surgeries"):
        surgery_parts = [f"{s['name']} ({s['status']})" for s in patient_data["Surgeries"]]
        parts.append("Surgeries: " + ", ".join(surgery_parts))
    if patient_data.get("Allergies"):
        parts.append("Allergies: " + ", ".join(patient_data["Allergies"]))
    if patient_data.get("Medical_Warnings"):
        parts.append("Medical warnings: " + ", ".join(patient_data["Medical_Warnings"]))
    if patient_data.get("Problems"):
        parts.append("Comorbidities: " + ", ".join(patient_data["Problems"]))
    if patient_data.get("Vitals"):
        vitals = patient_data["Vitals"]
        vitals_text = ", ".join([f"{k} {v}" for k, v in vitals.items()])
        parts.append("Vital signs: " + vitals_text)
    if patient_data.get("Lab_Results"):
        parts.append("Lab results: " + json.dumps(patient_data["Lab_Results"], indent=2))
    
    return ". ".join(parts)


def get_user_prompt(patient_data: Dict[str, Any]) -> str:
    """User prompt containing formatted patient data - optimized for GPT-4."""
    patient_text = format_patient_data(patient_data)
    
    return f"""Transform the following structured patient data into a single, coherent clinical summary paragraph.

PATIENT DATA:
{patient_text}

INSTRUCTIONS:
1. Synthesize all provided information into one flowing paragraph
2. Start with patient demographics (age, gender) and primary diagnosis
3. Integrate symptoms, medications, allergies, and other clinical details naturally
4. Include vital signs and lab results if provided, formatted appropriately
5. Maintain exact medical terminology, abbreviations, and values
6. Ensure the paragraph reads as professional clinical documentation

Generate the clinical summary now:"""


def build_summary_prompt(patient_data: Dict[str, Any]) -> List[Dict[str, str]]:
    """Build complete prompt structure for OpenAI API."""
    return [
        {
            "role": "system",
            "content": get_system_prompt()
        },
        {
            "role": "user",
            "content": get_user_prompt(patient_data)
        }
    ]

