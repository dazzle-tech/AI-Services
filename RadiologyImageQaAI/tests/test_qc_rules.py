from app.config import Settings
from app.models import ExamType, MissingRegion, QCStatus, RequiredLandmark
from app.qc_rules import run_qc_for_exam_type


def test_fail_missing_diaphragm():
    settings = Settings()
    res = run_qc_for_exam_type(
        ExamType.CT_ABDOMEN_PELVIS,
        landmarks={
            "diaphragm_or_lung_bases_seen": False,
            "kidneys_seen": True,
            "bladder_seen": True,
            "pubic_symphysis_seen": True,
        },
        settings=settings,
    )
    assert res.qc_status == QCStatus.FAIL
    assert res.missing_region == MissingRegion.SUPERIOR_ABDOMEN
    assert res.required_landmark_not_seen == RequiredLandmark.DIAPHRAGM_OR_LUNG_BASES


def test_fail_missing_pubic_symphysis():
    settings = Settings()
    res = run_qc_for_exam_type(
        ExamType.CT_ABDOMEN_PELVIS,
        landmarks={
            "diaphragm_or_lung_bases_seen": True,
            "kidneys_seen": True,
            "bladder_seen": True,
            "pubic_symphysis_seen": False,
        },
        settings=settings,
    )
    assert res.qc_status == QCStatus.FAIL
    assert res.missing_region == MissingRegion.LOWER_PELVIS
    assert res.required_landmark_not_seen == RequiredLandmark.PUBIC_SYMPHYSIS


def test_warning_missing_bladder_default():
    settings = Settings(bladder_missing_is_fail=False)
    res = run_qc_for_exam_type(
        ExamType.CT_ABDOMEN_PELVIS,
        landmarks={
            "diaphragm_or_lung_bases_seen": True,
            "kidneys_seen": True,
            "bladder_seen": False,
            "pubic_symphysis_seen": True,
        },
        settings=settings,
    )
    assert res.qc_status == QCStatus.WARNING
    assert res.required_landmark_not_seen == RequiredLandmark.BLADDER


def test_warning_missing_kidneys():
    settings = Settings()
    res = run_qc_for_exam_type(
        ExamType.CT_ABDOMEN_PELVIS,
        landmarks={
            "diaphragm_or_lung_bases_seen": True,
            "kidneys_seen": False,
            "bladder_seen": True,
            "pubic_symphysis_seen": True,
        },
        settings=settings,
    )
    assert res.qc_status == QCStatus.WARNING
    assert res.required_landmark_not_seen == RequiredLandmark.KIDNEYS


def test_pass_all_landmarks():
    settings = Settings()
    res = run_qc_for_exam_type(
        ExamType.CT_ABDOMEN_PELVIS,
        landmarks={
            "diaphragm_or_lung_bases_seen": True,
            "kidneys_seen": True,
            "bladder_seen": True,
            "pubic_symphysis_seen": True,
        },
        settings=settings,
    )
    assert res.qc_status == QCStatus.PASS
    assert res.required_landmark_not_seen is None


def test_ct_chest_fail_missing_apices():
    settings = Settings()
    res = run_qc_for_exam_type(
        ExamType.CT_CHEST,
        landmarks={"lung_apices_seen": False, "lung_bases_seen": True},
        settings=settings,
    )
    assert res.qc_status == QCStatus.FAIL
    assert res.missing_region == MissingRegion.SUPERIOR_CHEST
    assert res.required_landmark_not_seen == RequiredLandmark.LUNG_APICES


def test_ct_head_fail_missing_skull_base():
    settings = Settings()
    res = run_qc_for_exam_type(
        ExamType.CT_HEAD,
        landmarks={"skull_vertex_seen": True, "skull_base_seen": False},
        settings=settings,
    )
    assert res.qc_status == QCStatus.FAIL
    assert res.missing_region == MissingRegion.INFERIOR_HEAD
    assert res.required_landmark_not_seen == RequiredLandmark.SKULL_BASE


def test_ct_abdomen_fail_missing_kidneys():
    settings = Settings()
    res = run_qc_for_exam_type(
        ExamType.CT_ABDOMEN,
        landmarks={
            "diaphragm_or_lung_bases_seen": True,
            "liver_dome_seen": True,
            "kidneys_seen": False,
        },
        settings=settings,
    )
    assert res.qc_status == QCStatus.FAIL
    assert res.missing_region == MissingRegion.MID_ABDOMEN
    assert res.required_landmark_not_seen == RequiredLandmark.KIDNEYS


def test_ct_cap_fail_missing_pubic_symphysis():
    settings = Settings()
    res = run_qc_for_exam_type(
        ExamType.CT_CHEST_ABDOMEN_PELVIS,
        landmarks={"lung_apices_seen": True, "pubic_symphysis_seen": False},
        settings=settings,
    )
    assert res.qc_status == QCStatus.FAIL
    assert res.missing_region == MissingRegion.LOWER_PELVIS
    assert res.required_landmark_not_seen == RequiredLandmark.PUBIC_SYMPHYSIS
