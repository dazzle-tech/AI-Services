from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Any

from ..interpretation.findings_schema import make_finding
from ..interpretation.models import Finding

logger = logging.getLogger(__name__)
MODEL_NAME = "gpt-4o-ct-vision"

try:
    from openai import OpenAI  # type: ignore
except Exception:  # pragma: no cover
    OpenAI = None  # type: ignore[assignment]

SYSTEM_PROMPT = """You are an expert radiologist AI assistant specializing in CT scan interpretation.
You will be shown multiple axial CT slices from a single study (presented left-to-right, superior-to-inferior).

RULES — follow every one without exception:
1. You are an ASSISTIVE AI only. You never confirm a diagnosis. You never state "no abnormality found" definitively.
2. Every finding must be labeled as a candidate finding requiring radiologist review.
3. Consider all provided slices together as one study before reporting.
4. CT-specific context:
   - Identify if contrast is present (bright vessels, enhanced structures).
   - Report HU ranges in finding_text only when clearly relevant (e.g., fat density, calcification).
   - For chest CT: evaluate lungs, mediastinum, pleura, and visible bones.
   - For abdominal CT: evaluate liver, spleen, kidneys, pancreas, bowel, vasculature, and lymph nodes.
   - For head CT: evaluate parenchyma, ventricles, sulci, and bone windows if visible.
   - For spine CT: evaluate vertebral bodies, disc spaces, canal, and neural foramina.
5. Assign priority:
   - CRITICAL: immediately life-threatening (aortic dissection, tension pneumothorax, herniation, active hemorrhage, complete bowel obstruction with ischemia)
   - URGENT: requires prompt attention (PE, significant pneumothorax, solid organ laceration, acute infarct, abscess, unstable fracture)
   - ROUTINE: warrants review (small nodule, mild effusion, degenerative changes, incidental finding)
6. The provided metadata is context only. Interpret only the anatomy actually visible in the images.
7. If the images do not match the requested exam/body part, set body_part_mismatch=true and explain briefly in mismatch_reason.
8. Do not invent abdominal-organ findings if abdominal organs are not visible or are poorly windowed. If the series is lung-window, state that abdominal soft-tissue interpretation is limited.
9. Output ONLY valid JSON — no preamble, no markdown.

OUTPUT FORMAT (strict JSON):
{
  "body_part": "<CHEST|ABDOMEN|HEAD|SPINE_CERVICAL|SPINE_THORACIC|SPINE_LUMBAR|PELVIS|NECK|EXTREMITY|ABDOMEN_PELVIS|CHEST_ABDOMEN_PELVIS|OTHER>",
  "contrast": "<WITH_CONTRAST|WITHOUT_CONTRAST|UNKNOWN>",
  "slice_count_reviewed": <integer — number of slices you were shown>,
  "image_quality": "<ADEQUATE|LIMITED — note any limiting factors>",
  "body_part_mismatch": <true|false>,
  "mismatch_reason": "<short explanation or null>",
  "findings": [
    {
      "finding_code": "<SNAKE_UPPER_CASE — e.g. PULMONARY_NODULE, PULMONARY_EMBOLISM, PLEURAL_EFFUSION, PNEUMOTHORAX, GROUND_GLASS_OPACITY, CONSOLIDATION, AORTIC_ANEURYSM, AORTIC_DISSECTION, PERICARDIAL_EFFUSION, LYMPHADENOPATHY, HEPATIC_LESION, SPLENIC_LESION, RENAL_LESION, ADRENAL_LESION, PANCREATIC_LESION, BOWEL_OBSTRUCTION, FREE_AIR, FREE_FLUID, ASCITES, ABDOMINAL_AORTIC_ANEURYSM, RETROPERITONEAL_MASS, INTRACRANIAL_HEMORRHAGE, CEREBRAL_EDEMA, MIDLINE_SHIFT, HYDROCEPHALUS, INFARCT, SUBDURAL_HEMATOMA, EPIDURAL_HEMATOMA, VERTEBRAL_FRACTURE, DISC_HERNIATION, SPINAL_STENOSIS, SOFT_TISSUE_MASS, BONE_LESION, LYMPH_NODE_ENLARGEMENT, VASCULAR_CALCIFICATION, FOREIGN_BODY, OTHER_FINDING>",
      "finding_text": "<one sentence: 'Possible X at Y. Radiologist review required.'>",
      "location": "<specific anatomical location, e.g. 'right lower lobe posterior segment', 'segment VII liver', 'L3-L4 disc space'>",
      "confidence": <float 0.0–1.0>,
      "priority": "<CRITICAL|URGENT|ROUTINE>"
    }
  ],
  "summary": "<3-4 sentence radiologist-style summary. Never use 'normal'. Start with 'CT of [body part]: AI candidate findings include...' or 'CT of [body part]: No AI candidate findings above threshold identified across reviewed slices. Radiologist review required.'>",
  "critical_alert": <true|false>
}

If the images are not recognizable as CT slices, return:
{
  "body_part": "UNKNOWN",
  "contrast": "UNKNOWN",
  "slice_count_reviewed": 0,
  "image_quality": "UNREADABLE",
  "body_part_mismatch": true,
  "mismatch_reason": "Images could not be interpreted as CT slices.",
  "findings": [],
  "summary": "Images could not be interpreted as CT slices. Radiologist review required.",
  "critical_alert": false
}"""


def run_gpt_ct_model(
    slice_png_paths: list[str],
    exam_type: str,
    metadata: dict[str, Any],
    openai_api_key: str,
    openai_model: str = "gpt-4o",
    openai_timeout: float = 30.0,
) -> tuple[list[Finding], dict[str, Any], dict[str, Any]]:
    """
    Send representative CT slice PNGs to GPT-4o and return structured findings.
    """
    if OpenAI is None:  # pragma: no cover
        raise RuntimeError("openai package is not installed")
    client = OpenAI(api_key=openai_api_key, timeout=openai_timeout)

    # Build image content blocks
    image_blocks: list[dict] = []
    for path_str in slice_png_paths:
        image_bytes = Path(path_str).read_bytes()
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        image_blocks.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "high"},
        })

    selected_series_meta = metadata.get("selected_series_meta") or {}
    context_text = (
        f"Requested exam type (context only): {exam_type}. "
        f"Selected series class (context only): {metadata.get('selected_series_class', 'UNKNOWN')}. "
        f"Study metadata: body_part={metadata.get('body_part_examined', 'UNKNOWN')}, "
        f"study_description={metadata.get('study_description', 'unknown')}, "
        f"series_description={selected_series_meta.get('series_description', metadata.get('series_description', 'unknown'))}, "
        f"window_center={selected_series_meta.get('window_center', metadata.get('window_center', 'unknown'))}, "
        f"window_width={selected_series_meta.get('window_width', metadata.get('window_width', 'unknown'))}, "
        f"convolution_kernel={selected_series_meta.get('convolution_kernel', metadata.get('convolution_kernel', 'unknown'))}, "
        f"contrast_agent={metadata.get('contrast_bolus_agent', 'not specified')}, "
        f"slice_thickness={metadata.get('slice_thickness', 'unknown')}mm, "
        f"total_slices_in_series={metadata.get('slice_count', 'unknown')}, "
        f"slices_shown_to_you={len(slice_png_paths)}. "
        "Analyze all slices together and return the JSON response."
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [*image_blocks, {"type": "text", "text": context_text}],
        },
    ]

    try:
        response = client.chat.completions.create(
            model=openai_model,
            max_tokens=2000,
            messages=messages,
            temperature=0.1,
        )
    except Exception as exc:
        exc_name = type(exc).__name__
        msg = str(exc).lower()
        if "Timeout" in exc_name or "timeout" in msg or "timed out" in msg:
            raise RuntimeError(
                "GPT-4o CT request timed out after 30s. "
                "Service returned REVIEW_REQUIRED."
            ) from exc
        raise

    raw_text = response.choices[0].message.content or ""
    clean = raw_text.strip()
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[-1]
        clean = clean.rsplit("```", 1)[0]
    clean = clean.strip()

    try:
        gpt_output = json.loads(clean)
    except json.JSONDecodeError as e:
        logger.error("GPT-4o CT returned non-JSON: %s", raw_text[:500])
        raise RuntimeError(f"GPT-4o returned invalid JSON: {e}") from e

    logger.debug("GPT raw output: %s", json.dumps(gpt_output))

    findings: list[Finding] = []
    for raw_finding in gpt_output.get("findings", []):
        try:
            confidence = float(raw_finding.get("confidence", 0.5))
            confidence = max(0.0, min(1.0, confidence))
            priority = raw_finding.get("priority", "ROUTINE").upper()
            if priority not in {"CRITICAL", "URGENT", "ROUTINE"}:
                priority = "ROUTINE"
            findings.append(
                make_finding(
                    finding_code=raw_finding.get("finding_code", "OTHER_FINDING"),
                    finding_text=raw_finding.get("finding_text", "Possible finding. Radiologist review required."),
                    location=raw_finding.get("location"),
                    confidence=confidence,
                    priority=priority,
                )
            )
        except Exception as e:
            logger.warning("Skipping malformed CT finding: %s", e)
            continue

    model_meta = {
        "name": MODEL_NAME,
        "body_part_detected": gpt_output.get("body_part", "UNKNOWN"),
        "image_quality": gpt_output.get("image_quality", "UNKNOWN"),
        "view_detected": "AXIAL",
    }

    return findings, gpt_output, model_meta
