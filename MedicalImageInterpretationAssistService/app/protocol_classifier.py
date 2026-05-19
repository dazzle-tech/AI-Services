from __future__ import annotations

from dataclasses import dataclass
import re


_WS_RE = re.compile(r"\s+")
SUPPORTED_EXAMS = ("XR_",)

XR_BODY_PART_MAP = {
    "HAND": ["hand", "finger", "thumb", "metacarpal", "phalanx"],
    "WRIST": ["wrist", "carpal", "distal radius"],
    "FOREARM": ["forearm", "radius", "ulna"],
    "ELBOW": ["elbow", "humerus distal", "olecranon"],
    "SHOULDER": ["shoulder", "clavicle", "scapula", "acromial", "glenohumeral"],
    "SPINE_CERVICAL": ["cervical", "c-spine", "c spine"],
    "SPINE_THORACIC": ["thoracic spine", "t-spine", "t spine"],
    "SPINE_LUMBAR": ["lumbar", "l-spine", "l spine", "lumbosacral"],
    "PELVIS": ["pelvis", "pelvic", "hip", "sacrum", "ilium", "ischium"],
    "FEMUR": ["femur", "thigh"],
    "KNEE": ["knee", "patella", "tibia proximal", "fibula proximal"],
    "TIBIA": ["tibia", "fibula", "lower leg"],
    "ANKLE": ["ankle", "talus", "calcaneus", "mortise"],
    "FOOT": ["foot", "toe", "metatarsal", "calcaneus"],
    "SKULL": ["skull", "facial bone", "mandible", "orbit", "nasal"],
    "KUB": [
        "kub",
        "kidney ureter bladder",
    ],
    "ABDOMEN": [
        "abdomen",
        "abdominal",
        "kub",
        "kidney ureter",
        "kidney",
        "urogram",
        "urinary",
        "pelvis kub",
        "intravenous pyelogram",
        "ivp",
        "nephrostogram",
        "renal",
        "bladder",
        "ureter",
        "cystogram",
    ],
    "CHEST": ["chest", "thorax", "rib", "sternum", "lung"],
}


VIEW_KEYWORD_MAP = {
    "AP": [
        "ap view",
        " ap ",
        "anteropost",
        "anteroposterior",
        "projection urogram",
        "urogram projection",
        "scout",
        "plain film",
        "kub ap",
    ],
    "PA": ["pa view", " pa ", "posteroanterior"],
    "LATERAL": ["lateral", " lat ", "latl"],
    "AXIAL": ["axial"],
    "OBLIQUE": ["oblique"],
    "DECUBITUS": ["decubitus"],
    "ERECT": ["erect", "upright", "standing"],
    "SUPINE": ["supine"],
    "MORTISE": ["mortise"],
    "SUNRISE": ["sunrise", "skyline"],
    "SWIMMERS": ["swimmers"],
    "ODONTOID": ["odontoid", "open mouth"],
    "SCAPULAR_Y": ["scapular y", "scapula y", "y view"],
}


def detect_view_from_text(text: str | None) -> str | None:
    combined = _norm(text)
    if not combined:
        return None
    padded = f" {combined} "
    for view, keywords in VIEW_KEYWORD_MAP.items():
        for kw in keywords:
            if kw in padded:
                return view
    return None


@dataclass(frozen=True)
class ExamClassification:
    exam_type: str
    view: str | None


def _norm(text: str | None) -> str:
    if not text:
        return ""
    out = text.lower().replace("\\", " ").replace("/", " ").replace("-", " ")
    return _WS_RE.sub(" ", out).strip()


def classify_exam_type(
    *,
    modality: str | None = None,
    study_description: str | None = None,
    series_description: str | None = None,
    protocol_name: str | None = None,
    body_part_examined: str | None = None,
) -> ExamClassification:
    mod = (modality or "").strip().upper()
    if mod not in {"CR", "DX"}:
        return ExamClassification(exam_type="UNSUPPORTED_MODALITY", view=None)

    combined_all = _norm(
        " ".join([s for s in [study_description, series_description, protocol_name, body_part_examined] if s])
    )
    view = detect_view_from_text(" ".join([s for s in [series_description, study_description] if s]))

    for body_part, keywords in XR_BODY_PART_MAP.items():
        for kw in keywords:
            if kw in combined_all:
                return ExamClassification(exam_type=f"XR_{body_part}", view=view)

    return ExamClassification(exam_type="XR_UNKNOWN", view=view)
