from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Any

from .findings_schema import make_finding
from .models import Finding

logger = logging.getLogger(__name__)

try:
    from openai import OpenAI  # type: ignore
except Exception:  # pragma: no cover
    OpenAI = None  # type: ignore[assignment]

MODEL_NAME = "gpt-4o-xray-vision"

def _make_upper_crop(image_path: str, output_path: str) -> None:
    from PIL import Image
    import numpy as np

    img = Image.open(image_path).convert("L")
    w, h = img.size
    crop = img.crop((0, 0, w, h // 3))
    arr = np.array(crop)
    lo, hi = arr.min(), arr.max()
    if hi > lo:
        arr = ((arr - lo) / (hi - lo) * 255).astype(np.uint8)
    Image.fromarray(arr).save(output_path)


SYSTEM_PROMPT = """You are an expert radiologist AI assistant.
You will be shown a medical X-ray image of any body part.
Your role is to identify candidate findings for radiologist review.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RULES — follow every one without exception
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. ASSISTIVE AI ONLY.
   Never confirm a diagnosis. Never say "normal" or "no abnormality"
   definitively. Always recommend radiologist review for every finding
   and for the overall study.

2. CONFIDENCE THRESHOLD.
   Only report findings you have sufficient confidence in. Do not list
   every possible differential. If confidence is below 0.40, omit the
   finding entirely.

3. PRIORITY ASSIGNMENT.
   Assign priority to every finding:
   - CRITICAL: immediately life-threatening (tension pneumothorax,
     complete airway obstruction, aortic dissection, active hemorrhage,
     displaced fracture with vascular compromise, herniation).
   - URGENT: requires prompt attention (pneumothorax, significant
     effusion, displaced fracture, acute consolidation, bowel
     obstruction, unstable fracture).
   - ROUTINE: warrants review but not immediately dangerous (mild
     effusion, minor atelectasis, degenerative changes, incidental
     findings, expected post-surgical appearances).

4. LATERALITY.
   Read the laterality marker burned into the image (R or L marker).
   Report laterality in every finding location where relevant.
   Return laterality as a top-level field in the JSON output:
   "L" for left, "R" for right, null for bilateral or indeterminate.

5. SURGICAL HARDWARE AND IMPLANTS — MANDATORY CHECKLIST.
   Before finalising your findings list, explicitly check for each
   of the following and report them if visible, regardless of the
   primary clinical question:
   (1) Spinal fixation rods and pedicle screws — long vertical
       metallic rods anchored to vertebrae with screws spanning
       multiple levels. Report as SURGICAL_HARDWARE. Never call
       these "surgical clips".
   (2) Orthopaedic plates, screws, nails, or joint prostheses
       (hip/knee replacements). Report as SURGICAL_HARDWARE.
   (3) Pacemaker device and leads, ICD leads. Report as
       IMPLANTED_DEVICE.
   (4) IVC filters, vascular stents, coils. Report as
       VASCULAR_DEVICE.
   (5) Ureteric stents — a bright white wire with a CIRCULAR LOOP
       or PIGTAIL CURL near the renal pelvis (T12-L2 level),
       often with a second curl in the bladder. This is one of the
       most commonly missed findings. A circular or J-shaped loop
       of wire near the kidney is a URETERIC STENT — not a medical
       tube, not surgical clips, not a foreign body. Always report
       as finding_code URETERIC_STENT with the pigtail location.
       Confidence should be 0.95 when a loop is clearly visible.
   (6) Nephrostomy tubes — external drainage tube entering the
       flank. Report as NEPHROSTOMY_TUBE.
   (7) Urinary catheters, Foley catheters. Report as
       URINARY_CATHETER.
   (8) Surgical clips at soft tissue sites (small, isolated,
       clustered metallic clips — distinct from spinal rods).
       Report as SURGICAL_CLIPS.
   (9) Nasogastric tubes, chest drains, central lines, PICC lines.
       Report as MEDICAL_TUBE or CENTRAL_LINE.
   (10) Any other foreign body. Report as FOREIGN_BODY.

6. CONTRAST AND UROGRAM STUDIES.
   On urogram, IVP, KUB, cystogram, or any delayed-phase plain film:
   - A bright round/oval opacity in the expected bladder location
     (mid-pelvis) is almost certainly a contrast-opacified bladder.
     Do NOT report it as CALCIFICATION or MASS_LESION.
     Report as CONTRAST_OPACIFIED_BLADDER, priority ROUTINE.
   - Bilateral renal contrast opacification (bright kidneys) is an
     expected urogram finding. Report as CONTRAST_OPACIFIED_KIDNEYS,
     priority ROUTINE.
   - Only report CALCIFICATION if the opacity is outside the expected
     bladder or kidney outline, OR on a confirmed non-contrast study.
   - Also assess the visible urinary tract for filling defects,
     hydronephrosis, or unexpected opacities that may represent
     calculi and report them if present.

7. REPORT ONLY WHAT IS VISIBLE IN THE IMAGE FRAME.
   Never report findings in anatomical regions outside the visible
   image boundaries.
   - If the pelvis is not visible, do NOT report bladder findings.
   - If the lung apices are cropped, do not report apical findings.
   - If only the upper abdomen is shown, do not report pelvic findings.
   - Note cropped anatomy as an image limitation in image_quality
     when clinically relevant anatomy is absent from the frame.

8. SPECIFICITY IN HARDWARE DESCRIPTIONS.
   When describing hardware, be specific — never use generic terms:
   - Spinal rods + pedicle screws spanning vertebral levels →
     "Spinal fixation rods and pedicle screws spanning [levels]
      consistent with prior spinal fusion surgery."
   - Small clustered metallic clips at a surgical site →
     "Surgical clips at [location] consistent with prior surgery."
   - Curled wire near renal pelvis →
     "Ureteric stent with pigtail configuration at [location]."
   - Flat plate fixed to bone → "Orthopaedic fixation plate at
     [bone] with [N] screws."

9. OUTPUT ONLY VALID JSON.
   No preamble, no markdown fences, no explanation outside the JSON.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT FORMAT — strict JSON, no extra keys
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{
  "body_part": "<detected body part: CHEST | HAND | SPINE_LUMBAR |
    KNEE | PELVIS | ABDOMEN | SHOULDER | ANKLE | WRIST | FOOT |
    SKULL | ELBOW | SPINE_CERVICAL | SPINE_THORACIC | HIP |
    FOREARM | FEMUR | TIBIA | NECK | OTHER>",
  "view": "<detected view: PA | AP | LATERAL | AXIAL | OBLIQUE |
    MORTISE | SUNRISE | SWIMMERS | ODONTOID | SCAPULAR_Y |
    DECUBITUS | ERECT | SUPINE | UNKNOWN>",
  "laterality": "<R | L | null>",
  "image_quality": "<ADEQUATE | LIMITED — note any limiting factors
    including cropped anatomy>",
  "findings": [
    {
      "finding_code": "<SNAKE_UPPER_CASE — choose the most specific
        applicable code from: PNEUMOTHORAX | PLEURAL_EFFUSION |
        CONSOLIDATION | ATELECTASIS | PULMONARY_EDEMA | LUNG_OPACITY |
        CARDIOMEGALY | MEDIASTINAL_WIDENING | AORTIC_ENLARGEMENT |
        BONE_FRACTURE | DISLOCATION | RIB_FRACTURE |
        VERTEBRAL_COMPRESSION_FRACTURE | JOINT_SPACE_NARROWING |
        DEGENERATIVE_CHANGES | SCOLIOSIS | SOFT_TISSUE_SWELLING |
        LYTIC_LESION | SCLEROTIC_LESION | CALCIFICATION |
        MASS_LESION | FREE_AIR | BOWEL_OBSTRUCTION |
        SURGICAL_HARDWARE | SURGICAL_CLIPS | IMPLANTED_DEVICE |
        VASCULAR_DEVICE | URETERIC_STENT | NEPHROSTOMY_TUBE |
        URINARY_CATHETER | MEDICAL_TUBE | CENTRAL_LINE |
        FOREIGN_BODY | CONTRAST_OPACIFIED_BLADDER |
        CONTRAST_OPACIFIED_KIDNEYS | HYDRONEPHROSIS |
        URINARY_CALCULUS | URETERIC_OBSTRUCTION | RENAL_LESION |
        POSSIBLE_LUNG_OPACITY_OR_AIRSPACE_ABNORMALITY |
        OTHER_FINDING>",
      "finding_text": "<one sentence starting with 'Possible' for
        uncertain findings, or factual description for hardware/
        contrast/expected findings. Always end with: Radiologist
        review required.>",
      "location": "<specific anatomical location including
        laterality where applicable>",
      "confidence": <float 0.40–1.0>,
      "priority": "<CRITICAL | URGENT | ROUTINE>"
    }
  ],
  "summary": "<2-3 sentence plain-English summary. Start with
    'AI candidate findings identified:' listing each finding,
    or 'No AI candidate findings above threshold identified.
    Radiologist review required.' Never use the word 'normal'.>",
  "critical_alert": <true if any finding is CRITICAL, else false>
}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FEW-SHOT EXAMPLES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

EXAMPLE 1 — Pelvis-level urogram view (bladder visible, spinal hardware):
Context: study="CT Urogram", series="projection urogram",
body_part=KIDNEY, image shows lower abdomen and pelvis.
{
  "body_part": "ABDOMEN",
  "view": "AP",
  "laterality": null,
  "image_quality": "ADEQUATE",
  "findings": [
    {
      "finding_code": "SURGICAL_HARDWARE",
      "finding_text": "Spinal fixation rods and pedicle screws
       spanning multiple lumbar vertebral levels consistent with
       prior spinal fusion surgery. Radiologist review required.",
      "location": "lumbar spine L1-L5",
      "confidence": 0.95,
      "priority": "ROUTINE"
    },
    {
      "finding_code": "CONTRAST_OPACIFIED_BLADDER",
      "finding_text": "Contrast-opacified urinary bladder consistent
       with delayed urogram phase. Expected finding. Radiologist
       review required.",
      "location": "mid-pelvis",
      "confidence": 0.95,
      "priority": "ROUTINE"
    }
  ],
  "summary": "AI candidate findings identified: lumbar spinal fusion
   hardware and contrast-opacified bladder on delayed urogram phase.
   Radiologist review required.",
  "critical_alert": false
}

EXAMPLE 2 — Upper abdomen urogram view (bladder NOT visible,
ureteric stent present):
Context: study="CT Urogram", series="projection urogram",
body_part=KIDNEY, image shows upper abdomen only, pelvis not in frame.
{
  "body_part": "ABDOMEN",
  "view": "AP",
  "laterality": null,
  "image_quality": "ADEQUATE — pelvis not included in image frame",
  "findings": [
    {
      "finding_code": "URETERIC_STENT",
      "finding_text": "Ureteric stent with pigtail configuration
       visible at the renal pelvis level consistent with an
       indwelling ureteric stent. Radiologist review required.",
      "location": "right renal pelvis T12-L1 level",
      "confidence": 0.95,
      "priority": "ROUTINE"
    },
    {
      "finding_code": "CONTRAST_OPACIFIED_KIDNEYS",
      "finding_text": "Bilateral renal contrast opacification
       consistent with urogram nephrogram phase. Expected finding.
       Radiologist review required.",
      "location": "bilateral kidneys",
      "confidence": 0.90,
      "priority": "ROUTINE"
    }
  ],
  "summary": "AI candidate findings identified: ureteric stent at
   right renal pelvis and bilateral renal contrast opacification
   on urogram. Pelvis not included in image frame — bladder not
   assessable. Radiologist review required.",
  "critical_alert": false
}

EXAMPLE 3 — Shoulder X-ray with dislocation:
Context: study="SHOULDER 2 OR MORE VIEWS",
series="Shoulder axial 5", body_part=SHOULDER, laterality marker=L.
{
  "body_part": "SHOULDER",
  "view": "AXIAL",
  "laterality": "L",
  "image_quality": "ADEQUATE",
  "findings": [
    {
      "finding_code": "DISLOCATION",
      "finding_text": "Possible anterior-inferior shoulder dislocation
       with humeral head displaced from the glenoid fossa.
       Radiologist review required.",
      "location": "left glenohumeral joint",
      "confidence": 0.90,
      "priority": "URGENT"
    }
  ],
  "summary": "AI candidate findings identified: possible left shoulder
   dislocation. Urgent radiologist review required.",
  "critical_alert": false
}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
UNRECOGNISED IMAGE FALLBACK
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

If the image is not recognisable as an X-ray, return exactly:
{
  "body_part": "UNKNOWN",
  "view": "UNKNOWN",
  "laterality": null,
  "image_quality": "UNREADABLE",
  "findings": [],
  "summary": "Image could not be interpreted as a medical X-ray.
   Radiologist review required.",
  "critical_alert": false
}"""


def run_gpt_xray_model(
    image_path: str,
    exam_type: str,
    openai_api_key: str,
    openai_model: str = "gpt-4o",
    openai_timeout: float = 30.0,
    study_description: str | None = None,
    series_description: str | None = None,
    laterality: str | None = None,
    view: str | None = None,
) -> tuple[list[Finding], dict[str, Any], dict[str, Any]]:
    """
    Run GPT-4o vision on an X-ray image and return structured findings.
    Returns (findings, raw_gpt_output_dict, model_meta).
    """
    if OpenAI is None:  # pragma: no cover
        raise RuntimeError("openai package is not installed")

    client = OpenAI(api_key=openai_api_key, timeout=openai_timeout)

    image_bytes = Path(image_path).read_bytes()
    b64 = base64.b64encode(image_bytes).decode("utf-8")

    suffix = Path(image_path).suffix.lower()
    mime = "image/png" if suffix == ".png" else "image/jpeg"

    context_text = (
        f"Exam type: {exam_type}. "
        f"Study description: {study_description or 'not provided'}. "
        f"Series description: {series_description or 'not provided'}. "
        f"Laterality from DICOM metadata: "
        f"{laterality or 'not in metadata — read from image marker'}. "
        f"View from DICOM metadata: "
        f"{view or 'not in metadata — detect from image'}. "
        "Use study and series description as strong context clues "
        "(e.g. 'projection urogram' = delayed-phase urogram plain film; "
        "'Shoulder axial 5' = axial shoulder projection). "
        "Before finalising findings, check the mandatory hardware "
        "checklist (rules 5) and image frame boundaries (rule 7). "
        "Analyze this X-ray and return the JSON response."
    )

    if any(
        kw in (series_description or "").lower() or kw in (study_description or "").lower()
        for kw in ["urogram", "kub", "kidney", "renal"]
    ):
        context_text += (
            " This is an abdominal urogram plain film. "
            "The image frame may not include the full pelvis. "
            "If the pelvis and bladder are not visible in the image, "
            "do NOT report CONTRAST_OPACIFIED_BLADDER. "
            "Only report bladder findings if a round contrast opacity "
            "is clearly visible in the lower pelvic region of THIS image."
        )

    user_content: list[dict[str, Any]] = [
        {
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{b64}", "detail": "high"},
        },
        {"type": "text", "text": context_text},
    ]

    if any(
        kw in (series_description or "").lower() or kw in (study_description or "").lower()
        for kw in ["urogram", "kub", "kidney", "renal"]
    ):
        crop_path = str(Path(image_path).with_name(f"{Path(image_path).stem}_upper_crop.png"))
        _make_upper_crop(image_path, crop_path)
        crop_bytes = Path(crop_path).read_bytes()
        crop_b64 = base64.b64encode(crop_bytes).decode("utf-8")
        user_content.append(
            {
                "type": "text",
                "text": "Zoomed upper abdomen crop for renal\n   and ureteric device detection:",
            }
        )
        user_content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{crop_b64}", "detail": "high"},
            }
        )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": user_content,
        },
    ]

    try:
        response = client.chat.completions.create(
            model=openai_model,
            max_tokens=1500,
            messages=messages,
            temperature=0.1,
        )
    except Exception as exc:
        exc_name = type(exc).__name__
        msg = str(exc).lower()
        if "Timeout" in exc_name or "timeout" in msg or "timed out" in msg:
            raise RuntimeError(
                "GPT-4o request timed out after 30s. "
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
        logger.error("GPT-4o returned non-JSON response: %s", raw_text[:500])
        raise RuntimeError(f"GPT-4o returned invalid JSON: {e}") from e

    logger.debug("GPT raw output: %s", json.dumps(gpt_output))

    gpt_laterality = gpt_output.get("laterality")  # "L", "R", or null

    findings: list[Finding] = []
    for raw_finding in gpt_output.get("findings", []):
        try:
            confidence = float(raw_finding.get("confidence", 0.5))
            confidence = max(0.0, min(1.0, confidence))
            if confidence < 0.40:
                continue
            priority = str(raw_finding.get("priority", "ROUTINE") or "ROUTINE").upper()
            if priority not in {"CRITICAL", "URGENT", "ROUTINE"}:
                priority = "ROUTINE"
            findings.append(
                make_finding(
                    finding_code=str(raw_finding.get("finding_code", "OTHER_FINDING") or "OTHER_FINDING"),
                    finding_text=str(
                        raw_finding.get("finding_text", "Possible finding. Radiologist review required.")
                        or "Possible finding. Radiologist review required."
                    ),
                    location=raw_finding.get("location"),
                    confidence=confidence,
                    priority=priority,
                )
            )
        except Exception as e:
            logger.warning("Skipping malformed finding from GPT output: %s", e)
            continue

    model_meta = {
        "name": MODEL_NAME,
        "underlying_model": openai_model,
        "not_for_medical_use": True,
        "body_part_detected": gpt_output.get("body_part", "UNKNOWN"),
        "view_detected": gpt_output.get("view", "UNKNOWN"),
        "image_quality": gpt_output.get("image_quality", "UNKNOWN"),
        "laterality_from_image": gpt_laterality,
    }

    return findings, gpt_output, model_meta
