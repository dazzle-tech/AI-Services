from app.protocol_classifier import classify_exam_type
from app.models import ExamType


def test_classify_ct_abdomen_pelvis_variants():
    assert classify_exam_type("CT Abdomen Pelvis With Contrast") == ExamType.CT_ABDOMEN_PELVIS
    assert classify_exam_type("CT abdomen/pelvis") == ExamType.CT_ABDOMEN_PELVIS
    assert classify_exam_type("CT A/P") == ExamType.CT_ABDOMEN_PELVIS
    assert classify_exam_type("Abdomen and Pelvis") == ExamType.CT_ABDOMEN_PELVIS
    assert classify_exam_type("ABD PELVIS") == ExamType.CT_ABDOMEN_PELVIS


def test_classify_other_types():
    assert classify_exam_type("CT Chest") == ExamType.CT_CHEST
    assert classify_exam_type("CT Head Without Contrast") == ExamType.CT_HEAD
    assert classify_exam_type("MRI Lumbar Spine") == ExamType.MRI_LUMBAR_SPINE


def test_classify_unknown():
    assert classify_exam_type("US Abdomen") == ExamType.UNKNOWN


def test_classify_xray_from_text():
    assert classify_exam_type("XR Knee") == ExamType.XRAY
    assert classify_exam_type("CXR Portable") == ExamType.XRAY
    assert classify_exam_type("X-ray chest") == ExamType.XRAY


def test_classify_from_modality_and_descriptions_ct_ap():
    assert (
        classify_exam_type(
            modality="CT",
            study_description="CT ABDOMEN",
            series_description="PELVIS W/CONTRAST",
        )
        == ExamType.CT_ABDOMEN_PELVIS
    )


def test_classify_from_modality_and_descriptions_ct_chest():
    assert (
        classify_exam_type(
            modality="CT",
            study_description="CT Chest",
            series_description=None,
        )
        == ExamType.CT_CHEST
    )


def test_classify_from_modality_and_descriptions_non_ct_unknown():
    assert (
        classify_exam_type(
            modality="MR",
            study_description="Abdomen Pelvis",
            series_description="",
        )
        == ExamType.UNKNOWN
    )


def test_classify_from_modality_xray_variants():
    assert (
        classify_exam_type(
            modality="DX",
            study_description="Knee",
            series_description="AP",
        )
        == ExamType.XRAY_UNKNOWN
    )
    assert (
        classify_exam_type(
            modality="CR",
            study_description="CHEST",
            series_description="PA",
        )
        == ExamType.XR_CHEST
    )


def test_classify_from_modality_chest_view_positions():
    assert (
        classify_exam_type(
            modality="DX",
            study_description="CHEST",
            body_part_examined="CHEST",
            view_position="PA",
        )
        == ExamType.XR_CHEST_PA
    )
    assert (
        classify_exam_type(
            modality="DX",
            study_description="CHEST",
            body_part_examined="CHEST",
            view_position="AP",
        )
        == ExamType.XR_CHEST_AP
    )
    assert (
        classify_exam_type(
            modality="CR",
            study_description="CHEST",
            body_part_examined="CHEST",
            view_position="LAT",
        )
        == ExamType.XR_CHEST_LATERAL
    )


def test_classify_ct_abdomen_only():
    assert (
        classify_exam_type(
            modality="CT",
            study_description="CT Abdomen",
            series_description="ABDOMEN W CONTRAST",
            protocol_name="ABD",
            body_part_examined="ABDOMEN",
        )
        == ExamType.CT_ABDOMEN
    )


def test_classify_ct_head():
    assert (
        classify_exam_type(
            modality="CT",
            study_description="CT Head without contrast",
            series_description="HEAD",
            protocol_name="CT HEAD",
            body_part_examined="HEAD",
        )
        == ExamType.CT_HEAD
    )


def test_classify_ct_chest_abdomen_pelvis():
    assert (
        classify_exam_type(
            modality="CT",
            study_description="CT Chest Abdomen Pelvis",
            series_description="CAP",
            protocol_name="CT CAP",
            body_part_examined="CHEST/ABDOMEN/PELVIS",
        )
        == ExamType.CT_CHEST_ABDOMEN_PELVIS
    )
