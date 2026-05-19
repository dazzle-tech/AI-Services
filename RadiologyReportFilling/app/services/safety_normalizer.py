"""Safety normalizer: deterministic post-processing of raw model output.

Implements the "Safety-Normalized Output" sibling of the raw model JSON.
Critical: confidence, priority, and critical_alert MUST be derived here
from structured signals, never copied from the model's probability claims.
"""
import logging
import re
from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import DISCLAIMER_TEXT
from app.models.schemas import (
    AssistiveResponse,
    Finding,
    Icd10Match,
    RadLexMatch,
    RagGrounding,
    SafetyNormalizedOutput,
    Warning_,
)

logger = logging.getLogger(__name__)


# Anatomic regions used for metadata-vs-text mismatch detection.
_ANATOMY_KEYWORDS = {
    "CHEST": ["chest", "lung", "pulmonary", "thoracic", "rib", "mediastinum", "pleural", "pneumothorax"],
    "ABDOMEN": ["abdomen", "abdominal", "bowel", "intestine", "peritoneal", "pneumoperitoneum"],
    "PELVIS": ["pelvis", "pelvic"],
    "WRIST": ["wrist", "carpal"],
    "HAND": ["hand", "finger", "metacarpal"],
    "KNEE": ["knee", "patella"],
    "ANKLE": ["ankle", "talus"],
    "HEAD": ["head", "brain", "skull", "cranium"],
    "SPINE": ["spine", "vertebra", "cervical", "thoracic spine", "lumbar"],
}

# Findings that drive critical_alert=true (matches docstring in medical_terms_guide.txt).
_CRITICAL_FINDING_PATTERNS = [
    r"\bpneumothorax\b",
    r"\btension pneumothorax\b",
    r"\bpneumoperitoneum\b",
    r"\bfree (intraperitoneal )?air\b",
    r"\baortic dissection\b",
    r"\bwidened mediastinum\b",
    r"\bmainstem (intubation|bronchus)\b",
    r"\bmisplaced (et|ng|central) (tube|line)\b",
    r"\bmediastinal shift\b",
]


def _normalize_body_part(metadata: Dict[str, Any]) -> Optional[str]:
    """Pull a canonical body-part token from common DICOM tag names."""
    for key in ("BodyPartExamined", "body_part_examined", "bodyPartExamined"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().upper()
    return None


def _text_anatomy_signals(text: str) -> List[str]:
    """Return the set of canonical anatomy buckets mentioned in `text`."""
    lower = text.lower()
    hits: List[str] = []
    for region, kws in _ANATOMY_KEYWORDS.items():
        if any(kw in lower for kw in kws):
            hits.append(region)
    return hits


def _detect_laterality_conflict(text_a: str, text_b: str) -> bool:
    """Return True if one text mentions LEFT-anatomy and the other RIGHT-anatomy.

    Conservative: requires both `left|right` AND a shared anatomy bucket.
    """
    a_lower, b_lower = text_a.lower(), text_b.lower()
    a_left = bool(re.search(r"\bleft[- ]", a_lower))
    a_right = bool(re.search(r"\bright[- ]", a_lower))
    b_left = bool(re.search(r"\bleft[- ]", b_lower))
    b_right = bool(re.search(r"\bright[- ]", b_lower))
    cross_conflict = (a_left and b_right) or (a_right and b_left)
    if not cross_conflict:
        return False
    shared = set(_text_anatomy_signals(text_a)) & set(_text_anatomy_signals(text_b))
    return bool(shared)


_NEGATION_TOKENS = (
    "no",
    "not",
    "without",
    "negative",
    "negative for",
    "denies",
    "ruled out",
    "r/o",
    "no evidence of",
    "no sign of",
    "absent",
    "free of",
    "unremarkable for",
)


def _is_negated(text_lower: str, match_start: int) -> bool:
    """Return True if a negation token appears in the ~6 words preceding `match_start`."""
    window = text_lower[max(0, match_start - 60):match_start]
    return any(neg in window for neg in _NEGATION_TOKENS)


def _is_critical_text(text: str) -> bool:
    """Return True if any non-negated critical-taxonomy phrase appears in `text`."""
    lower = text.lower()
    for pattern in _CRITICAL_FINDING_PATTERNS:
        for m in re.finditer(pattern, lower):
            if not _is_negated(lower, m.start()):
                return True
    return False


def _is_single_frontal_view(metadata: Dict[str, Any], exam_type: Optional[str]) -> bool:
    """Heuristic: is this study a single frontal (PA or AP) view?"""
    view = str(metadata.get("ViewPosition", "")).upper()
    if view not in ("PA", "AP"):
        return False
    desc = " ".join(str(v) for v in [exam_type, metadata.get("StudyDescription", "")]).lower()
    if "lateral" in desc or "two view" in desc or "2 view" in desc or "pa/lateral" in desc:
        return False
    return True


def _unwrap_if_wrapped(raw: Dict[str, Any]) -> Dict[str, Any]:
    """If the model wrapped its response in the response envelope, peel it off.

    The model occasionally returns {raw_model_output, safety_normalized_output,
    disclaimer} instead of the inner content directly. Prefer the inner
    content (raw_model_output or safety_normalized_output) when that happens.
    """
    if not isinstance(raw, dict):
        return raw
    envelope_keys = {"raw_model_output", "safety_normalized_output", "disclaimer"}
    if envelope_keys.issubset(set(raw.keys())):
        inner = raw.get("safety_normalized_output") or raw.get("raw_model_output")
        if isinstance(inner, dict):
            logger.warning("Model wrapped output in envelope; unwrapping.")
            return inner
    return raw


# Canonical severity per warning code. The safety normalizer overrides whatever
# the model says with these values so that downstream confidence/priority math is
# deterministic and a model that under-rates a finding cannot suppress an alert.
_CANONICAL_WARNING_SEVERITY = {
    "LATERALITY_CONFLICT": "high",
    "AI_SIZE_VARIANCE": "high",
    "AI_FINDING_DROPPED": "high",
    "ANATOMY_METADATA_MISMATCH": "critical",
    "MISSING_VIEW": "high",
    "SINGLE_VIEW_LIMITATION": "info",
    "SHORTHAND_EXPANDED": "info",
    "SPELLING_CORRECTED": "info",
    "AI_ENRICHMENT_APPLIED": "info",
}


def _coerce_warnings(raw_warnings: Any) -> List[Warning_]:
    """Coerce model-returned warnings into Warning_ objects with canonical severities.

    For codes in the canonical taxonomy, the normalizer forces the canonical
    severity regardless of what the model returned. Unknown codes keep their
    model-reported severity (defaulting to "info" if missing/malformed).
    """
    out: List[Warning_] = []
    if not isinstance(raw_warnings, list):
        return out
    for item in raw_warnings:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code", "UNSPECIFIED"))
        if code in _CANONICAL_WARNING_SEVERITY:
            severity = _CANONICAL_WARNING_SEVERITY[code]
        else:
            severity = item.get("severity", "info")
            if severity not in ("info", "high", "critical"):
                severity = "info"
        message = str(item.get("message", ""))
        if message:
            out.append(Warning_(severity=severity, code=code, message=message))
    return out


def _coerce_findings(raw_findings: Any, default_source: str) -> List[Finding]:
    """Coerce model-returned findings into Finding objects, dropping malformed entries."""
    out: List[Finding] = []
    if not isinstance(raw_findings, list):
        return out
    for item in raw_findings:
        if not isinstance(item, dict) or not item.get("label"):
            continue
        source = item.get("source", default_source)
        if source not in ("doctor", "radiologist", "clinical_report", "ai", "reconciled"):
            source = default_source
        try:
            out.append(
                Finding(
                    label=str(item["label"]),
                    location=item.get("location"),
                    status=item.get("status"),
                    size_cm=item.get("size_cm"),
                    source=source,
                )
            )
        except (TypeError, ValueError):
            continue
    return out


def _coerce_rag(raw: Any) -> RagGrounding:
    """Coerce the model's rag_grounding block into a RagGrounding object."""
    if not isinstance(raw, dict):
        return RagGrounding()
    icd: List[Icd10Match] = []
    for item in raw.get("icd10_codes", []) or []:
        if isinstance(item, dict) and item.get("code") and item.get("term"):
            icd.append(
                Icd10Match(
                    code=str(item["code"]),
                    term=str(item["term"]),
                    matched_phrase=str(item.get("matched_phrase", "")),
                )
            )
    radlex: List[RadLexMatch] = []
    for item in raw.get("radlex_terms", []) or []:
        if isinstance(item, dict) and item.get("id") and item.get("term"):
            radlex.append(
                RadLexMatch(
                    id=str(item["id"]),
                    term=str(item["term"]),
                    matched_phrase=str(item.get("matched_phrase", "")),
                )
            )
    return RagGrounding(icd10_codes=icd, radlex_terms=radlex)


def _strip_lobe_localization(findings: List[Finding]) -> Tuple[List[Finding], bool]:
    """Trim lobe-specific localization on single-view studies.

    Returns the trimmed findings and a bool indicating whether anything changed.
    """
    lobe_re = re.compile(
        r"\b(right|left)\s+(upper|middle|lower)\s+lobe\b|\b(RUL|LUL|RML|RLL|LLL)\b",
        re.IGNORECASE,
    )
    changed = False
    new_findings: List[Finding] = []
    for f in findings:
        if f.location and lobe_re.search(f.location):
            generic = f.location
            generic = lobe_re.sub("lung", generic)
            new_findings.append(f.model_copy(update={"location": generic}))
            changed = True
        else:
            new_findings.append(f)
    return new_findings, changed


def _compute_confidence(
    warnings: List[Warning_], anatomy_mismatch: bool, laterality_conflict: bool
) -> str:
    """Derive qualitative confidence from structured warning signals."""
    has_critical = anatomy_mismatch or any(w.severity == "critical" for w in warnings)
    if has_critical or laterality_conflict:
        return "Low"
    if any(w.severity == "high" for w in warnings):
        return "Medium"
    return "High"


def _compute_priority(
    critical_alert: bool, warnings: List[Warning_]
) -> str:
    """Priority is Urgent if critical_alert or any critical-severity warning fires."""
    if critical_alert or any(w.severity == "critical" for w in warnings):
        return "Urgent"
    return "Routine"


def normalize_correction(
    raw: Dict[str, Any],
    doctor_notes: str,
    radiologist_notes: str,
    exam_type: Optional[str],
    dicom_metadata: Dict[str, Any],
) -> AssistiveResponse:
    """Normalize raw model output from the report-correction endpoint."""
    raw_copy = deepcopy(raw)
    raw = _unwrap_if_wrapped(raw)

    findings = _coerce_findings(raw.get("findings"), default_source="radiologist")
    warnings = _coerce_warnings(raw.get("warnings"))
    rag = _coerce_rag(raw.get("rag_grounding"))

    if _detect_laterality_conflict(doctor_notes, radiologist_notes):
        if not any(w.code == "LATERALITY_CONFLICT" for w in warnings):
            warnings.append(
                Warning_(
                    severity="high",
                    code="LATERALITY_CONFLICT",
                    message=(
                        "Doctor's note and radiologist's note disagree on laterality "
                        "(left vs right) for the same anatomic region. Confirm before signoff."
                    ),
                )
            )
        laterality_conflict = True
    else:
        laterality_conflict = False

    body_part = _normalize_body_part(dicom_metadata)
    combined_text = f"{doctor_notes}\n{radiologist_notes}"
    anatomy_mismatch = False
    if body_part and body_part in _ANATOMY_KEYWORDS:
        signals = _text_anatomy_signals(combined_text)
        if signals and body_part not in signals:
            anatomy_mismatch = True
            warnings.append(
                Warning_(
                    severity="critical",
                    code="ANATOMY_METADATA_MISMATCH",
                    message=(
                        f"DICOM BodyPartExamined='{body_part}' but report text describes "
                        f"{', '.join(signals)}. Possible mislabeled study."
                    ),
                )
            )

    if _is_single_frontal_view(dicom_metadata, exam_type):
        findings, trimmed = _strip_lobe_localization(findings)
        if trimmed:
            warnings.append(
                Warning_(
                    severity="info",
                    code="SINGLE_VIEW_LIMITATION",
                    message=(
                        "Only a single frontal view available; lobe-level localization "
                        "trimmed in findings (preserved verbatim in the corrected notes)."
                    ),
                )
            )

    critical_alert = anatomy_mismatch or _is_critical_text(combined_text)
    confidence = _compute_confidence(warnings, anatomy_mismatch, laterality_conflict)
    priority = _compute_priority(critical_alert, warnings)

    spelling = raw.get("spelling_corrections")
    if not isinstance(spelling, dict):
        spelling = {}

    structured = raw.get("structured_report")
    if not isinstance(structured, dict):
        structured = None

    normalized = SafetyNormalizedOutput(
        study_metadata=dicom_metadata or {},
        exam_type=str(raw.get("exam_type") or exam_type or "Unspecified"),
        findings=findings,
        confidence=confidence,
        priority=priority,
        warnings=warnings,
        critical_alert=critical_alert,
        rag_grounding=rag,
        corrected_doctor_notes=raw.get("corrected_doctor_notes") or doctor_notes,
        corrected_radiologist_notes=raw.get("corrected_radiologist_notes") or radiologist_notes,
        structured_report=structured,
        spelling_corrections=spelling or None,
    )

    return AssistiveResponse(
        raw_model_output=raw_copy,
        safety_normalized_output=normalized,
        disclaimer=DISCLAIMER_TEXT,
    )


def normalize_matching(
    raw: Dict[str, Any],
    clinical_report: str,
    ai_image_analysis: Dict[str, Any],
    dicom_metadata: Dict[str, Any],
) -> AssistiveResponse:
    """Normalize raw model output from the analysis-matching endpoint."""
    raw_copy = deepcopy(raw)
    raw = _unwrap_if_wrapped(raw)

    findings = _coerce_findings(raw.get("findings"), default_source="reconciled")
    warnings = _coerce_warnings(raw.get("warnings"))
    rag = _coerce_rag(raw.get("rag_grounding"))

    body_part = _normalize_body_part(dicom_metadata)
    text_blob = clinical_report + " " + str(ai_image_analysis.get("detected_anatomy", ""))
    anatomy_mismatch = False
    if body_part and body_part in _ANATOMY_KEYWORDS:
        signals = _text_anatomy_signals(text_blob)
        if signals and body_part not in signals:
            anatomy_mismatch = True
            if not any(w.code == "ANATOMY_METADATA_MISMATCH" for w in warnings):
                warnings.append(
                    Warning_(
                        severity="critical",
                        code="ANATOMY_METADATA_MISMATCH",
                        message=(
                            f"DICOM BodyPartExamined='{body_part}' but content describes "
                            f"{', '.join(signals)}. Possible mislabeled study."
                        ),
                    )
                )

    if _is_single_frontal_view(dicom_metadata, None):
        findings, trimmed = _strip_lobe_localization(findings)
        if trimmed and not any(w.code == "SINGLE_VIEW_LIMITATION" for w in warnings):
            warnings.append(
                Warning_(
                    severity="info",
                    code="SINGLE_VIEW_LIMITATION",
                    message=(
                        "Only a single frontal view available; lobe-level localization "
                        "trimmed beyond what the clinical_report documents."
                    ),
                )
            )

    critical_alert = anatomy_mismatch or _is_critical_text(clinical_report)

    if isinstance(raw.get("ai_findings_dropped"), list) and raw["ai_findings_dropped"]:
        if not any(w.code == "AI_FINDING_DROPPED" for w in warnings):
            warnings.append(
                Warning_(
                    severity="high",
                    code="AI_FINDING_DROPPED",
                    message=(
                        f"{len(raw['ai_findings_dropped'])} AI finding(s) dropped because they "
                        "contradicted the authoritative clinical report."
                    ),
                )
            )

    if isinstance(raw.get("ai_findings_used_for_enrichment"), list) and raw[
        "ai_findings_used_for_enrichment"
    ]:
        if not any(w.code == "AI_ENRICHMENT_APPLIED" for w in warnings):
            warnings.append(
                Warning_(
                    severity="info",
                    code="AI_ENRICHMENT_APPLIED",
                    message=(
                        f"{len(raw['ai_findings_used_for_enrichment'])} AI finding(s) used to "
                        "enrich the clinical report with non-conflicting detail."
                    ),
                )
            )

    confidence = _compute_confidence(warnings, anatomy_mismatch, laterality_conflict=False)
    priority = _compute_priority(critical_alert, warnings)

    reconciled = raw.get("reconciled_findings") if isinstance(raw.get("reconciled_findings"), list) else None
    dropped = raw.get("ai_findings_dropped") if isinstance(raw.get("ai_findings_dropped"), list) else None
    enriched = (
        raw.get("ai_findings_used_for_enrichment")
        if isinstance(raw.get("ai_findings_used_for_enrichment"), list)
        else None
    )

    normalized = SafetyNormalizedOutput(
        study_metadata=dicom_metadata or {},
        exam_type=str(raw.get("exam_type") or "Unspecified"),
        findings=findings,
        confidence=confidence,
        priority=priority,
        warnings=warnings,
        critical_alert=critical_alert,
        rag_grounding=rag,
        reconciled_findings=reconciled,
        ai_findings_dropped=dropped,
        ai_findings_used_for_enrichment=enriched,
    )

    return AssistiveResponse(
        raw_model_output=raw_copy,
        safety_normalized_output=normalized,
        disclaimer=DISCLAIMER_TEXT,
    )
