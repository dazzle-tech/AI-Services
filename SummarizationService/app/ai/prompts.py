"""Prompt templates for clinical summary generation."""
import json
from typing import Dict, Any, List

from app.core.config import settings


def _uses_qwen3_thinking_model() -> bool:
    """
    Qwen3-family models (served locally via Ollama in this setup) think by
    default: they emit a <think>...</think> reasoning block before the
    actual answer, and those reasoning tokens count against max_tokens. With
    a low max_tokens budget the model can burn the whole budget "thinking"
    and return an empty content field. Appending "/no_think" to the prompt
    is the documented way to disable this for Qwen3. This should only be
    applied for Qwen3 models - it would just be inert clutter in a prompt
    sent to a non-Qwen provider (e.g. real GPT-4/GPT-4o).
    """
    model_name = (settings.openai_model or "").lower()
    return "qwen3" in model_name or "qwen" in model_name


def get_system_prompt() -> str:
    """System prompt optimized for GPT-4o clinical summary generation."""
    return """You are an expert medical documentation AI specialized in creating concise, coherent clinical summary paragraphs using GPT-4.

Your task is to transform structured patient data into a single, well-written clinical summary paragraph that:
- Reads naturally and professionally
- Preserves all medical terminology, abbreviations, and values exactly as provided
- Maintains clinical accuracy and completeness
- Flows logically from patient demographics through clinical findings

CRITICAL REQUIREMENTS:
1. FIDELITY (MOST IMPORTANT RULE): ONLY use information explicitly present in the PATIENT DATA below.
   - Never invent, infer, guess, or "fill in" typical/plausible values for a condition (no invented drug names, dosages, lab values, vital signs, or symptoms).
   - If a category (symptoms, medications, vitals, labs, allergies, etc.) is not present in PATIENT DATA, do NOT mention it at all - do not say "no known allergies" or similar unless that was explicitly stated in the input.
   - Every number, unit, and named entity in your output MUST appear, in some form, in PATIENT DATA. If you are not sure a detail was given, leave it out.
2. PRECISION: Preserve exact medical abbreviations (e.g., "BID", "PRN", "STEMI"), numbers, units, and terminology exactly as given - do not convert, calculate, or estimate new values.
3. STRUCTURE: Create ONE coherent paragraph that flows naturally.
4. LANGUAGE: Use professional medical documentation style - clear, concise, objective.
5. LENGTH: The summary should be as long as the available data supports and no longer. Sparse input (e.g., only age/gender/diagnosis) should produce a short 1-2 sentence summary. Do not pad the summary with generic or invented clinical detail to reach a target length.

OUTPUT FORMAT:
- Return ONLY the clinical summary text - no labels, headers, or meta-commentary
- Start directly with patient description (e.g., "A 45-year-old male...")
- End with a complete sentence - no trailing fragments"""


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
    
    prompt = f"""Transform the following structured patient data into a single, coherent clinical summary paragraph.

PATIENT DATA:
{patient_text}

INSTRUCTIONS:
1. Synthesize only the information shown above into one flowing paragraph
2. Start with patient demographics (age, gender) and primary diagnosis
3. Integrate symptoms, medications, allergies, and other clinical details naturally - but only if they appear above
4. Include vital signs and lab results only if they appear above, formatted appropriately
5. Maintain exact medical terminology, abbreviations, and values as given - do not add, estimate, or infer new ones
6. If the data above is limited to demographics and diagnosis, write a brief 1-2 sentence summary and stop - do not invent additional clinical detail to make the summary longer

Generate the clinical summary now:"""

    if _uses_qwen3_thinking_model():
        prompt += "\n\n/no_think"

    return prompt


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

