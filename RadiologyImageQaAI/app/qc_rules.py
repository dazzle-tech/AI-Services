from __future__ import annotations

from dataclasses import dataclass

from .config import Settings
from .models import ExamType, MissingRegion, QCStatus, RequiredLandmark


@dataclass(frozen=True)
class CoverageRuleResult:
    qc_status: QCStatus
    missing_region: MissingRegion | None
    required_landmark_not_seen: RequiredLandmark | None
    confidence: float
    recommended_action: str
    human_review_required: bool


def _base_confidence(*, derived_from_segmentation: bool) -> float:
    return 0.7 if derived_from_segmentation else 0.95


def evaluate_ct_chest_coverage(
    *,
    landmarks: dict,
    settings: Settings,
    derived_from_segmentation: bool = False,
) -> CoverageRuleResult:
    apices = bool(landmarks.get("lung_apices_seen"))
    bases = bool(landmarks.get("lung_bases_seen"))
    confidence = _base_confidence(derived_from_segmentation=derived_from_segmentation)

    if not apices:
        return CoverageRuleResult(
            qc_status=QCStatus.FAIL,
            missing_region=MissingRegion.SUPERIOR_CHEST,
            required_landmark_not_seen=RequiredLandmark.LUNG_APICES,
            confidence=confidence,
            recommended_action="Acquire additional superior images to include the lung apices before the patient leaves.",
            human_review_required=True,
        )

    if not bases:
        return CoverageRuleResult(
            qc_status=QCStatus.FAIL,
            missing_region=MissingRegion.INFERIOR_CHEST,
            required_landmark_not_seen=RequiredLandmark.LUNG_BASES,
            confidence=confidence,
            recommended_action="Acquire additional inferior images to include the lung bases before the patient leaves.",
            human_review_required=True,
        )

    return CoverageRuleResult(
        qc_status=QCStatus.PASS,
        missing_region=None,
        required_landmark_not_seen=None,
        confidence=confidence,
        recommended_action="No action required.",
        human_review_required=False,
    )


def evaluate_ct_head_coverage(
    *,
    landmarks: dict,
    settings: Settings,
    derived_from_segmentation: bool = False,
) -> CoverageRuleResult:
    vertex = bool(landmarks.get("skull_vertex_seen"))
    base = bool(landmarks.get("skull_base_seen"))
    confidence = _base_confidence(derived_from_segmentation=derived_from_segmentation)

    if not vertex:
        return CoverageRuleResult(
            qc_status=QCStatus.FAIL,
            missing_region=MissingRegion.SUPERIOR_HEAD,
            required_landmark_not_seen=RequiredLandmark.SKULL_VERTEX,
            confidence=confidence,
            recommended_action="Acquire additional superior images to include the skull vertex before the patient leaves.",
            human_review_required=True,
        )

    if not base:
        return CoverageRuleResult(
            qc_status=QCStatus.FAIL,
            missing_region=MissingRegion.INFERIOR_HEAD,
            required_landmark_not_seen=RequiredLandmark.SKULL_BASE,
            confidence=confidence,
            recommended_action="Acquire additional inferior images to include the skull base before the patient leaves.",
            human_review_required=True,
        )

    return CoverageRuleResult(
        qc_status=QCStatus.PASS,
        missing_region=None,
        required_landmark_not_seen=None,
        confidence=confidence,
        recommended_action="No action required.",
        human_review_required=False,
    )


def evaluate_ct_abdomen_coverage(
    *,
    landmarks: dict,
    settings: Settings,
    derived_from_segmentation: bool = False,
) -> CoverageRuleResult:
    diaphragm = bool(landmarks.get("diaphragm_or_lung_bases_seen"))
    liver_dome = bool(landmarks.get("liver_dome_seen"))
    kidneys = bool(landmarks.get("kidneys_seen"))
    confidence = _base_confidence(derived_from_segmentation=derived_from_segmentation)

    if not diaphragm:
        return CoverageRuleResult(
            qc_status=QCStatus.FAIL,
            missing_region=MissingRegion.SUPERIOR_ABDOMEN,
            required_landmark_not_seen=RequiredLandmark.DIAPHRAGM_OR_LUNG_BASES,
            confidence=confidence,
            recommended_action="Acquire additional superior images to include the diaphragm/lung bases before the patient leaves.",
            human_review_required=True,
        )

    if not liver_dome:
        return CoverageRuleResult(
            qc_status=QCStatus.FAIL,
            missing_region=MissingRegion.SUPERIOR_ABDOMEN,
            required_landmark_not_seen=RequiredLandmark.LIVER_DOME,
            confidence=confidence,
            recommended_action="Acquire additional superior images to include the liver dome before the patient leaves.",
            human_review_required=True,
        )

    if not kidneys:
        return CoverageRuleResult(
            qc_status=QCStatus.FAIL,
            missing_region=MissingRegion.MID_ABDOMEN,
            required_landmark_not_seen=RequiredLandmark.KIDNEYS,
            confidence=confidence,
            recommended_action="Acquire additional images to include both kidneys before the patient leaves.",
            human_review_required=True,
        )

    return CoverageRuleResult(
        qc_status=QCStatus.PASS,
        missing_region=None,
        required_landmark_not_seen=None,
        confidence=confidence,
        recommended_action="No action required.",
        human_review_required=False,
    )


def evaluate_ct_abdomen_pelvis_coverage(
    *,
    landmarks: dict,
    settings: Settings,
    derived_from_segmentation: bool = False,
) -> CoverageRuleResult:
    """
    MVP rules for anatomical coverage quality-checking.
    NOT diagnostic. Coverage-only.
    """
    diaphragm = bool(landmarks.get("diaphragm_or_lung_bases_seen"))
    pubic = bool(landmarks.get("pubic_symphysis_seen"))
    bladder = bool(landmarks.get("bladder_seen"))
    kidneys = bool(landmarks.get("kidneys_seen"))

    confidence = _base_confidence(derived_from_segmentation=derived_from_segmentation)

    if not diaphragm:
        return CoverageRuleResult(
            qc_status=QCStatus.FAIL,
            missing_region=MissingRegion.SUPERIOR_ABDOMEN,
            required_landmark_not_seen=RequiredLandmark.DIAPHRAGM_OR_LUNG_BASES,
            confidence=confidence,
            recommended_action=(
                "Acquire additional superior images to include the diaphragm/lung bases before the patient leaves."
            ),
            human_review_required=True,
        )

    if not pubic:
        return CoverageRuleResult(
            qc_status=QCStatus.FAIL,
            missing_region=MissingRegion.LOWER_PELVIS,
            required_landmark_not_seen=RequiredLandmark.PUBIC_SYMPHYSIS,
            confidence=confidence,
            recommended_action=(
                "Acquire additional lower pelvis images through the pubic symphysis before the patient leaves."
            ),
            human_review_required=True,
        )

    # Warnings
    if not bladder:
        status = QCStatus.FAIL if settings.bladder_missing_is_fail else QCStatus.WARNING
        return CoverageRuleResult(
            qc_status=status,
            missing_region=None,
            required_landmark_not_seen=RequiredLandmark.BLADDER,
            confidence=confidence,
            recommended_action=(
                "Review inferior coverage; consider acquiring additional images to include the urinary bladder."
            ),
            human_review_required=True,
        )

    if not kidneys:
        return CoverageRuleResult(
            qc_status=QCStatus.WARNING,
            missing_region=None,
            required_landmark_not_seen=RequiredLandmark.KIDNEYS,
            confidence=confidence,
            recommended_action="Review superior abdominal coverage; consider acquiring additional images to include both kidneys.",
            human_review_required=True,
        )

    return CoverageRuleResult(
        qc_status=QCStatus.PASS,
        missing_region=None,
        required_landmark_not_seen=None,
        confidence=confidence,
        recommended_action="No action required.",
        human_review_required=False,
    )


def evaluate_ct_chest_abdomen_pelvis_coverage(
    *,
    landmarks: dict,
    settings: Settings,
    derived_from_segmentation: bool = False,
) -> CoverageRuleResult:
    apices = bool(landmarks.get("lung_apices_seen"))
    pubic = bool(landmarks.get("pubic_symphysis_seen"))
    confidence = _base_confidence(derived_from_segmentation=derived_from_segmentation)

    if not apices:
        return CoverageRuleResult(
            qc_status=QCStatus.FAIL,
            missing_region=MissingRegion.SUPERIOR_CHEST,
            required_landmark_not_seen=RequiredLandmark.LUNG_APICES,
            confidence=confidence,
            recommended_action="Acquire additional superior images to include the lung apices before the patient leaves.",
            human_review_required=True,
        )

    if not pubic:
        return CoverageRuleResult(
            qc_status=QCStatus.FAIL,
            missing_region=MissingRegion.LOWER_PELVIS,
            required_landmark_not_seen=RequiredLandmark.PUBIC_SYMPHYSIS,
            confidence=confidence,
            recommended_action="Acquire additional lower pelvis images through the pubic symphysis before the patient leaves.",
            human_review_required=True,
        )

    return CoverageRuleResult(
        qc_status=QCStatus.PASS,
        missing_region=None,
        required_landmark_not_seen=None,
        confidence=confidence,
        recommended_action="No action required.",
        human_review_required=False,
    )


def run_qc_for_exam_type(
    exam_type: ExamType,
    *,
    landmarks: dict,
    settings: Settings,
    derived_from_segmentation: bool = False,
) -> CoverageRuleResult:
    if exam_type == ExamType.CT_CHEST:
        return evaluate_ct_chest_coverage(
            landmarks=landmarks, settings=settings, derived_from_segmentation=derived_from_segmentation
        )
    if exam_type == ExamType.CT_HEAD:
        return evaluate_ct_head_coverage(
            landmarks=landmarks, settings=settings, derived_from_segmentation=derived_from_segmentation
        )
    if exam_type == ExamType.CT_ABDOMEN:
        return evaluate_ct_abdomen_coverage(
            landmarks=landmarks, settings=settings, derived_from_segmentation=derived_from_segmentation
        )
    if exam_type == ExamType.CT_ABDOMEN_PELVIS:
        return evaluate_ct_abdomen_pelvis_coverage(
            landmarks=landmarks, settings=settings, derived_from_segmentation=derived_from_segmentation
        )
    if exam_type == ExamType.CT_CHEST_ABDOMEN_PELVIS:
        return evaluate_ct_chest_abdomen_pelvis_coverage(
            landmarks=landmarks, settings=settings, derived_from_segmentation=derived_from_segmentation
        )

    return CoverageRuleResult(
        qc_status=QCStatus.REVIEW_REQUIRED,
        missing_region=None,
        required_landmark_not_seen=None,
        confidence=0.0,
        recommended_action="Unsupported protocol for automated QC; route to human review.",
        human_review_required=True,
    )
