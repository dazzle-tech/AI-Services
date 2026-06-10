"""Focused tests for DICOM/order mismatch helpers in the workflow."""
import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "main.py"
SPEC = importlib.util.spec_from_file_location("radiology_workflow_main", MODULE_PATH)
assert SPEC and SPEC.loader
workflow_main = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = workflow_main
SPEC.loader.exec_module(workflow_main)


def test_build_dicom_order_mismatch_context_flags_cross_study_mismatch():
    context = workflow_main._build_dicom_order_mismatch_context(
        {
            "accession_number": "ACC-10015",
            "study_instance_uid": "1.2.840.10008.1.2.3.15",
        },
        order_accession="ACC-10008",
        radiologist_notes=(
            "Previous study reviewed under accession ACC-10008. "
            "StudyInstanceUID=1.2.840.10008.1.2.3.8"
        ),
        order_metadata={"AccessionNumber": "ACC-10008", "StudyInstanceUID": "1.2.840.10008.1.2.3.8"},
    )

    assert context["dicom_order_mismatch"] is True
    assert context["dicom_order_mismatch_warning"] == workflow_main._DICOM_ORDER_MISMATCH_WARNING
    assert context["DICOMAccessionNumber"] == "ACC-10015"
    assert context["StudyInstanceUID"] == "1.2.840.10008.1.2.3.15"
    assert context["dicom_order_mismatch_reasons"]


def test_build_dicom_order_mismatch_context_stays_clean_for_same_study():
    context = workflow_main._build_dicom_order_mismatch_context(
        {
            "accession_number": "ACC-10008",
            "study_instance_uid": "1.2.840.10008.1.2.3.8",
        },
        order_accession="ACC-10008",
        radiologist_notes="Comparison study StudyInstanceUID=1.2.840.10008.1.2.3.8",
        order_metadata={"AccessionNumber": "ACC-10008", "StudyInstanceUID": "1.2.840.10008.1.2.3.8"},
    )

    assert context["dicom_order_mismatch"] is False
    assert context["dicom_order_mismatch_warning"] is None
    assert context["dicom_order_mismatch_reasons"] is None


def test_build_delivery_preview_prefixes_subject_when_mismatch_warning_exists():
    preview = workflow_main._build_delivery_preview(
        {"TEMPLATE_TEXT": "report", "TEMPLATE_NAME": "RADIOLOGY REPORT"},
        exam_type="Chest X-ray",
        accession_number="ACC-10015",
        patient_id="P123",
        qc_status="PASS",
        dicom_order_mismatch_warning=workflow_main._DICOM_ORDER_MISMATCH_WARNING,
    )

    assert preview["subject"].startswith(workflow_main._DICOM_ORDER_MISMATCH_SUBJECT_PREFIX)
    assert "report" in preview["body"]
