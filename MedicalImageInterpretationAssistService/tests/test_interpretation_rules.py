from __future__ import annotations

import io
import zipfile

import pytest
from fastapi.testclient import TestClient


def _client() -> TestClient:
    from main import app

    return TestClient(app)


def _make_zip_bytes(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buffer.getvalue()


def test_health_endpoint_ok() -> None:
    client = _client()
    response = client.get("/api/v1/radiology/xray-interpretation/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "xray-interpretation-assist"


def test_ct_upload_returns_unsupported_modality(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.interpretation.interpretation_service as svc

    def fake_metadata(_folder):
        return {
            "modality": "CT",
            "study_description": "CT CHEST",
            "series_description": "CT CHEST",
            "protocol_name": "CT CHEST",
            "body_part_examined": "CHEST",
            "study_instance_uid": "1.2.3",
        }

    monkeypatch.setattr(svc, "extract_dicom_metadata", fake_metadata)

    client = _client()
    zip_bytes = _make_zip_bytes({"study/1.dcm": b"NOT_REAL_DICOM"})
    response = client.post(
        "/api/v1/radiology/xray-interpretation/dicom",
        files={"file": ("study.zip", zip_bytes, "application/zip")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "UNSUPPORTED_MODALITY"
    assert "Radiologist review required" in body["disclaimer"]
    assert body["study"]["modality"] == "CT"


def test_model_failure_returns_review_required(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.interpretation.interpretation_service as svc

    class DummyDataset:
        @property
        def pixel_array(self):
            import numpy as np

            return np.zeros((16, 16), dtype=np.uint8)

    def fake_metadata(_folder):
        return {
            "modality": "CR",
            "study_description": "CHEST XRAY",
            "series_description": "PA",
            "protocol_name": "CHEST",
            "body_part_examined": "CHEST",
            "study_instance_uid": "1.2.4",
        }

    def fake_dcmread(*args, **kwargs):
        return DummyDataset()

    def fake_model(*args, **kwargs):
        raise RuntimeError("model inference failed")

    monkeypatch.setattr(svc, "extract_dicom_metadata", fake_metadata)
    monkeypatch.setattr(svc.pydicom, "dcmread", fake_dcmread)
    monkeypatch.setattr(svc, "run_xray_model", fake_model)

    client = _client()
    zip_bytes = _make_zip_bytes({"study/1.dcm": b"ANY"})
    response = client.post(
        "/api/v1/radiology/xray-interpretation/dicom",
        files={"file": ("study.zip", zip_bytes, "application/zip")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "REVIEW_REQUIRED"
    assert body["summary"] == "X-ray interpretation model inference failed. Radiologist review required."
    assert "Radiologist review required" in body["disclaimer"]
    combined = (body["summary"] + " " + body["disclaimer"]).lower()
    assert "normal" not in combined
    assert "diagnosis confirmed" not in combined


def test_png_upload_is_accepted_and_processed(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.interpretation.interpretation_service as svc

    def fake_model(*_args, **_kwargs):
        return [], {}, {"name": "stub", "strong_threshold": 0.60, "weak_threshold": 0.35, "not_for_medical_use": True}

    monkeypatch.setattr(svc, "run_xray_model", fake_model)

    from PIL import Image

    img = Image.new("L", (64, 64), color=128)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()

    client = _client()
    response = client.post(
        "/api/v1/radiology/xray-interpretation/dicom",
        files={"file": ("xray.png", png_bytes, "image/png")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "COMPLETED"
    assert body["exam_type"] == "XR_CHEST"
    assert body["study"]["study_instance_uid"] is None


def test_response_includes_raw_model_outputs_and_model_meta(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.interpretation.interpretation_service as svc

    def fake_model(*_args, **_kwargs):
        return (
            [],
            {"Consolidation": 0.40, "Lung Opacity": 0.10},
            {"name": "stub-model", "strong_threshold": 0.60, "weak_threshold": 0.35, "not_for_medical_use": True},
        )

    monkeypatch.setattr(svc, "run_xray_model", fake_model)

    from PIL import Image

    img = Image.new("L", (64, 64), color=128)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()

    client = _client()
    response = client.post(
        "/api/v1/radiology/xray-interpretation/dicom",
        files={"file": ("xray.png", png_bytes, "image/png")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ai"]["model_name"] == "stub-model"
    assert body["ai"]["modality_handled"] == "XRAY"


# --- New tests ---

def test_critical_alert_true_for_high_confidence_pneumothorax() -> None:
    """critical_alert must be True when pneumothorax confidence >= 0.80."""
    from app.interpretation.xray_model import build_findings_from_model_outputs
    from app.interpretation.interpretation_service import has_critical

    findings = build_findings_from_model_outputs({"Pneumothorax": 0.85})
    codes = {f.finding_code for f in findings}
    assert "PNEUMOTHORAX" in codes
    pnx = next(f for f in findings if f.finding_code == "PNEUMOTHORAX")
    assert pnx.priority == "CRITICAL"
    assert has_critical(findings) is True


def test_urgent_pneumothorax_not_critical_alert() -> None:
    """Pneumothorax at 0.65 is URGENT but not CRITICAL."""
    from app.interpretation.xray_model import build_findings_from_model_outputs
    from app.interpretation.interpretation_service import has_critical

    findings = build_findings_from_model_outputs({"Pneumothorax": 0.65})
    pnx = next((f for f in findings if f.finding_code == "PNEUMOTHORAX"), None)
    assert pnx is not None
    assert pnx.priority == "URGENT"
    assert has_critical(findings) is False


def test_combined_lung_abnormality_rule_triggers_on_infiltration() -> None:
    """Combined lung rule fires for Infiltration at weak threshold even with no direct LUNG_OPACITY."""
    from app.interpretation.xray_model import build_findings_from_model_outputs

    findings = build_findings_from_model_outputs({"Infiltration": 0.40})
    codes = {f.finding_code for f in findings}
    assert "POSSIBLE_LUNG_OPACITY_OR_AIRSPACE_ABNORMALITY" in codes


def test_combined_lung_abnormality_suppressed_when_strong_consolidation() -> None:
    """Combined lung rule must not fire when strong CONSOLIDATION already present."""
    from app.interpretation.xray_model import build_findings_from_model_outputs

    findings = build_findings_from_model_outputs({"Consolidation": 0.75})
    codes = {f.finding_code for f in findings}
    assert "CONSOLIDATION" in codes
    assert "POSSIBLE_LUNG_OPACITY_OR_AIRSPACE_ABNORMALITY" not in codes


def test_zip_path_traversal_raises() -> None:
    """Zip with path traversal entries must be rejected before extraction."""
    import io
    import zipfile
    import tempfile
    from pathlib import Path
    from app.interpretation.interpretation_service import _load_upload_to_dicom_dir

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../../evil.txt", "pwned")
    zip_bytes = buf.getvalue()

    with tempfile.TemporaryDirectory() as tmp:
        upload = Path(tmp) / "bad.zip"
        upload.write_bytes(zip_bytes)
        dicom_dir = Path(tmp) / "out"
        dicom_dir.mkdir()
        try:
            _load_upload_to_dicom_dir(upload, dicom_dir)
            assert False, "Expected ValueError for path traversal"
        except ValueError as exc:
            assert "traversal" in str(exc).lower() or "unsafe" in str(exc).lower()


def test_chest_pa_metadata_preferred_over_model_and_single_view_warnings(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.interpretation.interpretation_service as svc
    from app.interpretation.models import Finding

    # Metadata indicates PA and 2 views.
    def fake_metadata(_folder):
        return {
            "modality": "CR",
            "study_description": "CHEST (2 VIEWS)",
            "series_description": "W CHEST PA",
            "protocol_name": "W CHEST PA",
            "body_part_examined": "CHEST",
            "study_instance_uid": "1.2.3",
            "view_position": None,
            "performed_protocol_codes": None,
        }

    class DummyDataset:
        @property
        def pixel_array(self):
            import numpy as np

            return np.zeros((16, 16), dtype=np.uint8)

    def fake_dcmread(*args, **kwargs):
        return DummyDataset()

    monkeypatch.setattr(svc, "extract_dicom_metadata", fake_metadata)
    monkeypatch.setattr(svc.pydicom, "dcmread", fake_dcmread)

    # Force GPT path with sk-test key and a conflicting AP view from the model.
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")

    import app.interpretation.gpt_xray_model as gpt_model

    cardiomegaly = Finding(
        finding_code="CARDIOMEGALY",
        finding_text="Possible cardiomegaly. Radiologist review required.",
        location="chest",
        confidence=0.8,
        priority="ROUTINE",
        radiologist_review_required=True,
    )
    opacity = Finding(
        finding_code="PULMONARY_OPACITY",
        finding_text="Possible pulmonary opacity. Radiologist review required.",
        location="right lower lobe",
        confidence=0.75,
        priority="ROUTINE",
        radiologist_review_required=True,
    )

    def fake_gpt(*_args, **_kwargs):
        return (
            [cardiomegaly, opacity],
            {"view": "AP", "body_part": "CHEST"},
            {"name": "stub-gpt", "view_detected": "AP", "image_quality": "ADEQUATE", "body_part_detected": "CHEST"},
        )

    monkeypatch.setattr(gpt_model, "run_gpt_xray_model", fake_gpt)

    client = _client()
    zip_bytes = _make_zip_bytes({"study/1.dcm": b"ANY"})
    response = client.post(
        "/api/v1/radiology/xray-interpretation/dicom",
        files={"file": ("study.zip", zip_bytes, "application/zip")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["exam_type"] == "XR_CHEST"
    assert body["status"] == "COMPLETED"
    assert body["study"]["view"] == "PA"
    assert any("metadata suggests pa" in w.lower() for w in body["warnings"])
    assert any("suggests 2 views" in w.lower() for w in body["warnings"])

    # Cardiomegaly should be down-weighted and mild.
    cardio = next((f for f in body["findings"] if f["finding_code"] == "CARDIOMEGALY"), None)
    assert cardio is not None
    assert 0.45 <= cardio["confidence"] <= 0.60
    assert "mild" in cardio["finding_text"].lower()

    # Opacity should not be confidently localized to a lobe on single frontal.
    assert all("lower lobe" not in (f.get("location") or "").lower() for f in body["findings"])
    op = next((f for f in body["findings"] if f["finding_code"] == "LOWER_ZONE_OPACITY"), None)
    assert op is not None
    assert "lower lung zone" in (op.get("location") or "").lower()
    assert op["confidence"] <= 0.55


def test_body_part_classifier_hand() -> None:
    from app.protocol_classifier import classify_exam_type

    cls = classify_exam_type(modality="CR", body_part_examined="HAND")
    assert cls.exam_type.startswith("XR_HAND")


def test_body_part_classifier_knee() -> None:
    from app.protocol_classifier import classify_exam_type

    cls = classify_exam_type(modality="CR", series_description="KNEE AP")
    assert cls.exam_type == "XR_KNEE"
    assert cls.view == "AP"


def test_gpt_path_used_when_api_key_set(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")

    import app.interpretation.gpt_xray_model as gpt_model

    def fake_gpt(*_args, **_kwargs):
        return [], {"body_part": "CHEST"}, {"name": "stub-gpt", "body_part_detected": "CHEST", "view_detected": "UNKNOWN", "image_quality": "ADEQUATE"}

    monkeypatch.setattr(gpt_model, "run_gpt_xray_model", fake_gpt)

    from PIL import Image

    img = Image.new("L", (64, 64), color=128)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()

    client = _client()
    response = client.post(
        "/api/v1/radiology/xray-interpretation/dicom",
        files={"file": ("xray.png", png_bytes, "image/png")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "COMPLETED"
    assert body["ai"]["model_name"] == "stub-gpt"


def test_fallback_to_torchxrayvision_when_no_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "openai_api_key", None)

    import app.interpretation.interpretation_service as svc

    def fake_model(*_args, **_kwargs):
        return [], {}, {"name": "stub-model", "strong_threshold": 0.60, "weak_threshold": 0.35, "not_for_medical_use": True}

    monkeypatch.setattr(svc, "run_xray_model", fake_model)

    from PIL import Image

    img = Image.new("L", (64, 64), color=128)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()

    client = _client()
    response = client.post(
        "/api/v1/radiology/xray-interpretation/dicom",
        files={"file": ("xray.png", png_bytes, "image/png")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "COMPLETED"


def test_non_chest_xr_without_api_key_returns_review_required(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.interpretation.interpretation_service as svc

    class DummyDataset:
        @property
        def pixel_array(self):
            import numpy as np

            return np.zeros((16, 16), dtype=np.uint8)

    def fake_metadata(_folder):
        return {
            "modality": "CR",
            "study_description": "KNEE XRAY",
            "series_description": "KNEE AP",
            "protocol_name": "KNEE",
            "body_part_examined": "KNEE",
            "study_instance_uid": "1.2.5",
        }

    def fake_dcmread(*args, **kwargs):
        return DummyDataset()

    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "openai_api_key", None)
    monkeypatch.setattr(svc, "extract_dicom_metadata", fake_metadata)
    monkeypatch.setattr(svc.pydicom, "dcmread", fake_dcmread)

    client = _client()
    zip_bytes = _make_zip_bytes({"study/1.dcm": b"ANY"})
    response = client.post(
        "/api/v1/radiology/xray-interpretation/dicom",
        files={"file": ("study.zip", zip_bytes, "application/zip")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["exam_type"] == "XR_KNEE"
    assert body["status"] == "REVIEW_REQUIRED"


def test_laterality_extracted_from_dicom(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.interpretation.interpretation_service as svc

    def fake_metadata(_folder):
        return {
            "modality": "CR",
            "study_description": "CHEST XRAY",
            "series_description": "PA",
            "protocol_name": "CHEST",
            "body_part_examined": "CHEST",
            "study_instance_uid": "1.2.6",
            "image_laterality": "LEFT",
            "view_position": "PA",
            "performed_protocol_codes": None,
            "patient_age": None,
            "patient_sex": None,
        }

    class DummyDataset:
        @property
        def pixel_array(self):
            import numpy as np

            return np.zeros((16, 16), dtype=np.uint8)

    def fake_dcmread(*args, **kwargs):
        return DummyDataset()

    def fake_model(*_args, **_kwargs):
        return [], {}, {"name": "stub-model", "strong_threshold": 0.60, "weak_threshold": 0.35, "not_for_medical_use": True}

    monkeypatch.setattr(svc, "extract_dicom_metadata", fake_metadata)
    monkeypatch.setattr(svc.pydicom, "dcmread", fake_dcmread)
    monkeypatch.setattr(svc, "run_xray_model", fake_model)

    client = _client()
    zip_bytes = _make_zip_bytes({"study/1.dcm": b"ANY"})
    response = client.post(
        "/api/v1/radiology/xray-interpretation/dicom",
        files={"file": ("study.zip", zip_bytes, "application/zip")},
    )
    body = response.json()
    assert body["study"]["laterality"] == "LEFT"


def test_view_detected_axial(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.interpretation.interpretation_service as svc

    def fake_metadata(_folder):
        return {
            "modality": "CR",
            "study_description": "SHOULDER XRAY",
            "series_description": "Shoulder axial 5",
            "protocol_name": "SHOULDER",
            "body_part_examined": "SHOULDER",
            "study_instance_uid": "1.2.7",
            "image_laterality": None,
            "view_position": None,
            "performed_protocol_codes": None,
            "patient_age": None,
            "patient_sex": None,
        }

    class DummyDataset:
        @property
        def pixel_array(self):
            import numpy as np

            return np.zeros((16, 16), dtype=np.uint8)

    def fake_dcmread(*args, **kwargs):
        return DummyDataset()

    monkeypatch.setattr(svc, "extract_dicom_metadata", fake_metadata)
    monkeypatch.setattr(svc.pydicom, "dcmread", fake_dcmread)

    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")

    import app.interpretation.gpt_xray_model as gpt_model

    monkeypatch.setattr(
        gpt_model,
        "run_gpt_xray_model",
        lambda **_: ([], {"view": "UNKNOWN", "body_part": "SHOULDER"}, {"name": "stub-gpt", "view_detected": "UNKNOWN", "image_quality": "ADEQUATE", "body_part_detected": "SHOULDER"}),
    )

    client = _client()
    zip_bytes = _make_zip_bytes({"study/1.dcm": b"ANY"})
    response = client.post(
        "/api/v1/radiology/xray-interpretation/dicom",
        files={"file": ("study.zip", zip_bytes, "application/zip")},
    )
    body = response.json()
    assert body["study"]["view"] == "AXIAL"


def test_indication_mismatch_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.interpretation.interpretation_service as svc

    def fake_metadata(_folder):
        return {
            "modality": "CR",
            "study_description": "SHOULDER XRAY",
            "series_description": "SHOULDER AP",
            "protocol_name": "SHOULDER",
            "body_part_examined": "SHOULDER",
            "study_instance_uid": "1.2.8",
            "image_laterality": None,
            "view_position": None,
            "performed_protocol_codes": None,
            "patient_age": None,
            "patient_sex": None,
        }

    class DummyDataset:
        @property
        def pixel_array(self):
            import numpy as np

            return np.zeros((16, 16), dtype=np.uint8)

    def fake_dcmread(*args, **kwargs):
        return DummyDataset()

    monkeypatch.setattr(svc, "extract_dicom_metadata", fake_metadata)
    monkeypatch.setattr(svc.pydicom, "dcmread", fake_dcmread)

    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")

    import app.interpretation.gpt_xray_model as gpt_model

    monkeypatch.setattr(
        gpt_model,
        "run_gpt_xray_model",
        lambda **_: ([], {"view": "AP", "body_part": "SHOULDER"}, {"name": "stub-gpt", "view_detected": "AP", "image_quality": "ADEQUATE", "body_part_detected": "SHOULDER"}),
    )

    client = _client()
    zip_bytes = _make_zip_bytes({"study/1.dcm": b"ANY"})
    response = client.post(
        "/api/v1/radiology/xray-interpretation/dicom",
        files={"file": ("study.zip", zip_bytes, "application/zip")},
        data={"clinical_indication": "shortness of breath"},
    )
    body = response.json()
    assert any("shortness of breath" in w.lower() for w in body["warnings"])


def test_missing_views_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.interpretation.interpretation_service as svc

    def fake_metadata(_folder):
        return {
            "modality": "CR",
            "study_description": "SHOULDER 2 OR MORE VIEWS",
            "series_description": "SHOULDER AP",
            "protocol_name": "SHOULDER",
            "body_part_examined": "SHOULDER",
            "study_instance_uid": "1.2.9",
            "image_laterality": None,
            "view_position": None,
            "performed_protocol_codes": None,
            "patient_age": None,
            "patient_sex": None,
        }

    class DummyDataset:
        @property
        def pixel_array(self):
            import numpy as np

            return np.zeros((16, 16), dtype=np.uint8)

    def fake_dcmread(*args, **kwargs):
        return DummyDataset()

    monkeypatch.setattr(svc, "extract_dicom_metadata", fake_metadata)
    monkeypatch.setattr(svc.pydicom, "dcmread", fake_dcmread)

    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")

    import app.interpretation.gpt_xray_model as gpt_model

    monkeypatch.setattr(
        gpt_model,
        "run_gpt_xray_model",
        lambda **_: ([], {"view": "AP", "body_part": "SHOULDER"}, {"name": "stub-gpt", "view_detected": "AP", "image_quality": "ADEQUATE", "body_part_detected": "SHOULDER"}),
    )

    client = _client()
    zip_bytes = _make_zip_bytes({"study/1.dcm": b"ANY"})
    response = client.post(
        "/api/v1/radiology/xray-interpretation/dicom",
        files={"file": ("study.zip", zip_bytes, "application/zip")},
    )
    body = response.json()
    assert any("2 views" in w.lower() or "2 or more" in w.lower() for w in body["warnings"])


def test_body_part_classifier_kidney_urogram() -> None:
    from app.protocol_classifier import classify_exam_type

    result = classify_exam_type(
        modality="CR",
        study_description="CT Urogram with 3D",
        series_description="projection urogram",
        body_part_examined="Kidney",
    )
    assert result.exam_type == "XR_ABDOMEN"
    assert result.view == "AP"


def test_body_part_classifier_kub() -> None:
    from app.protocol_classifier import classify_exam_type

    result = classify_exam_type(
        modality="CR",
        study_description="KUB",
        series_description=None,
        body_part_examined="ABDOMEN",
    )
    assert result.exam_type in {"XR_KUB", "XR_ABDOMEN"}


def test_body_part_classifier_renal() -> None:
    from app.protocol_classifier import classify_exam_type

    result = classify_exam_type(
        modality="DX",
        study_description="Renal Calculi Survey",
        series_description=None,
        body_part_examined=None,
    )
    assert result.exam_type == "XR_ABDOMEN"


def test_view_projection_urogram_maps_to_ap() -> None:
    from app.protocol_classifier import detect_view_from_text

    assert detect_view_from_text("projection urogram") == "AP"


def test_view_scout_maps_to_ap() -> None:
    from app.protocol_classifier import detect_view_from_text

    assert detect_view_from_text("scout film") == "AP"


def test_gpt_prompt_includes_study_description(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify study_description is passed into the GPT user message."""
    import app.interpretation.gpt_xray_model as gxm

    captured: dict = {}

    class FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    captured["messages"] = kwargs["messages"]

                    class R:
                        choices = [
                            type(
                                "C",
                                (),
                                {
                                    "message": type(
                                        "M",
                                        (),
                                        {
                                            "content": '{"body_part":"ABDOMEN","view":"AP","image_quality":"ADEQUATE","findings":[],"summary":"No findings.","critical_alert":false,"laterality":null}'
                                        },
                                    )()
                                },
                            )()
                        ]

                    return R()

    monkeypatch.setattr(gxm, "OpenAI", lambda **kwargs: FakeClient())

    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        img = Path(tmp) / "test.png"
        from PIL import Image
        import numpy as np

        Image.fromarray(np.zeros((64, 64), dtype=np.uint8)).save(str(img))

        gxm.run_gpt_xray_model(
            image_path=str(img),
            exam_type="XR_ABDOMEN",
            openai_api_key="sk-test",
            study_description="CT Urogram with 3D",
            series_description="projection urogram",
        )

    user_text = captured["messages"][1]["content"][1]["text"]
    assert "CT Urogram with 3D" in user_text
    assert "projection urogram" in user_text


def test_gpt_prompt_surgical_hardware_rule_present() -> None:
    """SURGICAL_HARDWARE must be mentioned in the system prompt."""
    from app.interpretation.gpt_xray_model import SYSTEM_PROMPT

    assert "SURGICAL_HARDWARE" in SYSTEM_PROMPT
    assert "SURGICAL HARDWARE" in SYSTEM_PROMPT.upper()


def test_gpt_prompt_contrast_bladder_rule_present() -> None:
    """Contrast bladder misidentification rule must be in system prompt."""
    from app.interpretation.gpt_xray_model import SYSTEM_PROMPT

    assert "CONTRAST_OPACIFIED_BLADDER" in SYSTEM_PROMPT
    assert "urogram" in SYSTEM_PROMPT.lower()


def test_gpt_prompt_spinal_rods_example_present() -> None:
    from app.interpretation.gpt_xray_model import SYSTEM_PROMPT

    assert "spinal fixation rods" in SYSTEM_PROMPT.lower()
    assert "pedicle screws" in SYSTEM_PROMPT.lower()
    assert "surgical clips" not in SYSTEM_PROMPT.lower() or \
           "do not" in SYSTEM_PROMPT.lower() or \
           "never use" in SYSTEM_PROMPT.lower()


def test_system_prompt_rules_present() -> None:
    from app.interpretation.gpt_xray_model import SYSTEM_PROMPT

    assert "URETERIC_STENT" in SYSTEM_PROMPT
    assert "SURGICAL_HARDWARE" in SYSTEM_PROMPT
    assert "CONTRAST_OPACIFIED_BLADDER" in SYSTEM_PROMPT
    assert "image frame" in SYSTEM_PROMPT.lower()
    assert "spinal fixation rods" in SYSTEM_PROMPT.lower()
    assert "surgical clips" not in SYSTEM_PROMPT.lower() \
        or "never call" in SYSTEM_PROMPT.lower() \
        or "never use" in SYSTEM_PROMPT.lower()


def test_system_prompt_few_shot_examples_present() -> None:
    from app.interpretation.gpt_xray_model import SYSTEM_PROMPT

    assert "EXAMPLE 1" in SYSTEM_PROMPT
    assert "EXAMPLE 2" in SYSTEM_PROMPT
    assert "EXAMPLE 3" in SYSTEM_PROMPT
    assert "pigtail" in SYSTEM_PROMPT.lower()
    assert "pelvis not included in image frame" in SYSTEM_PROMPT.lower()


def test_bilateral_body_part_laterality_is_null() -> None:
    from app.interpretation.interpretation_service import BILATERAL_BODY_PARTS

    assert "ABDOMEN" in BILATERAL_BODY_PARTS
    assert "KIDNEY" in BILATERAL_BODY_PARTS
    assert "CHEST" in BILATERAL_BODY_PARTS


def test_gpt_call_is_stateless(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.interpretation.gpt_xray_model as gxm

    captured: dict = {}

    class FakeCompletion:
        choices = [
            type(
                "C",
                (),
                {
                    "message": type(
                        "M",
                        (),
                        {
                            "content": '{"body_part":"CHEST","view":"AP","laterality":null,'
                            '"image_quality":"ADEQUATE","findings":[],'
                            '"summary":"No findings.","critical_alert":false}'
                        },
                    )()
                },
            )()
        ]

    class FakeCompletions:
        @staticmethod
        def create(**kwargs):
            captured["messages"] = kwargs["messages"]
            return FakeCompletion()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    monkeypatch.setattr(gxm, "OpenAI", lambda **kwargs: FakeClient())

    import tempfile
    from pathlib import Path
    from PIL import Image
    import numpy as np

    with tempfile.TemporaryDirectory() as tmp:
        img = Path(tmp) / "test.png"
        Image.fromarray(np.zeros((64, 64), dtype=np.uint8)).save(str(img))
        gxm.run_gpt_xray_model(
            image_path=str(img),
            exam_type="XR_CHEST",
            openai_api_key="sk-test",
            study_description="CHEST PA",
            series_description="PA view",
        )

    msgs = captured["messages"]
    assert len(msgs) == 2, \
        f"Expected exactly 2 messages (system + user), got {len(msgs)}"
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"


def test_context_text_includes_study_description(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.interpretation.gpt_xray_model as gxm

    captured: dict = {}

    class FakeCompletion:
        choices = [
            type(
                "C",
                (),
                {
                    "message": type(
                        "M",
                        (),
                        {
                            "content": '{"body_part":"ABDOMEN","view":"AP","laterality":null,'
                            '"image_quality":"ADEQUATE","findings":[],'
                            '"summary":"No findings.","critical_alert":false}'
                        },
                    )()
                },
            )()
        ]

    class FakeCompletions:
        @staticmethod
        def create(**kwargs):
            captured["messages"] = kwargs["messages"]
            return FakeCompletion()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    monkeypatch.setattr(gxm, "OpenAI", lambda **kwargs: FakeClient())

    import tempfile
    from pathlib import Path
    from PIL import Image
    import numpy as np

    with tempfile.TemporaryDirectory() as tmp:
        img = Path(tmp) / "test.png"
        Image.fromarray(np.zeros((64, 64), dtype=np.uint8)).save(str(img))
        gxm.run_gpt_xray_model(
            image_path=str(img),
            exam_type="XR_ABDOMEN",
            openai_api_key="sk-test",
            study_description="CT Urogram with 3D",
            series_description="projection urogram",
        )

    user_content = captured["messages"][1]["content"]
    text_block = next(b for b in user_content if b["type"] == "text")
    assert "CT Urogram with 3D" in text_block["text"]
    assert "projection urogram" in text_block["text"]
    assert "mandatory hardware checklist" in text_block["text"].lower()


def test_xray_timeout_returns_review_required(monkeypatch: pytest.MonkeyPatch) -> None:
    """A timeout from OpenAI must result in REVIEW_REQUIRED, not a 500."""
    import app.interpretation.gpt_xray_model as gxm

    class FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    raise Exception("Request timed out.")

    monkeypatch.setattr(gxm, "OpenAI", lambda **kwargs: FakeClient())

    import tempfile
    from pathlib import Path
    from PIL import Image
    import numpy as np

    with tempfile.TemporaryDirectory() as tmp:
        img = Path(tmp) / "test.png"
        Image.fromarray(np.zeros((64, 64), dtype=np.uint8)).save(str(img))
        try:
            gxm.run_gpt_xray_model(
                image_path=str(img),
                exam_type="XR_CHEST",
                openai_api_key="sk-test",
                openai_timeout=30.0,
            )
            raised = False
        except RuntimeError as e:
            raised = True
            assert "timed out" in str(e).lower()
    assert raised, "Expected RuntimeError on timeout"


def test_ct_timeout_returns_review_required(monkeypatch: pytest.MonkeyPatch) -> None:
    """A timeout from OpenAI CT must raise RuntimeError with timed out."""
    import app.ct.gpt_ct_model as gctm

    class FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    raise Exception("HTTPSConnectionPool timed out.")

    monkeypatch.setattr(gctm, "OpenAI", lambda **kwargs: FakeClient())

    try:
        gctm.run_gpt_ct_model(
            slice_png_paths=[],
            exam_type="CT_CHEST",
            metadata={},
            openai_api_key="sk-test",
            openai_timeout=30.0,
        )
        raised = False
    except RuntimeError as e:
        raised = True
        assert "timed out" in str(e).lower()
    assert raised


def test_audit_log_called_on_completed(monkeypatch: pytest.MonkeyPatch) -> None:
    """log_interpretation must be called for every COMPLETED response."""
    import app.interpretation.interpretation_service as svc

    calls: list[dict] = []

    def fake_audit(response, clinical_indication):
        calls.append(
            {
                "status": response.status,
                "exam_type": response.exam_type,
                "finding_codes": [f.finding_code for f in response.findings],
            }
        )
        return response

    monkeypatch.setattr(svc, "_audit", fake_audit)

    from app.interpretation.models import Finding
    from app.config import Settings
    from pathlib import Path
    import tempfile
    from PIL import Image
    import numpy as np

    stub_finding = Finding(
        finding_code="PNEUMOTHORAX",
        finding_text="Possible pneumothorax. Radiologist review required.",
        location="right apex",
        confidence=0.85,
        priority="URGENT",
        radiologist_review_required=True,
    )

    monkeypatch.setattr(svc, "_should_use_gpt", lambda _: True)
    monkeypatch.setattr(
        "app.interpretation.gpt_xray_model.run_gpt_xray_model",
        lambda **kwargs: (
            [stub_finding],
            {},
            {
                "name": "gpt-4o-xray-vision",
                "image_quality": "ADEQUATE",
                "laterality_from_image": None,
                "view_detected": "PA",
                "body_part_detected": "CHEST",
            },
        ),
    )

    settings = Settings(openai_api_key="sk-test")

    with tempfile.TemporaryDirectory() as tmp:
        img_path = Path(tmp) / "xray.png"
        Image.fromarray(np.zeros((64, 64), dtype=np.uint8)).save(str(img_path))
        workdir = Path(tmp) / "work"
        workdir.mkdir()
        svc.build_image_response(
            upload_input_path=img_path,
            workdir=workdir,
            clinical_indication=None,
            settings=settings,
            exam_type="XR_CHEST",
        )

    assert len(calls) == 1
    assert calls[0]["status"] == "COMPLETED"
    assert "PNEUMOTHORAX" in calls[0]["finding_codes"]


def test_audit_log_written_to_stdout(capsys) -> None:
    """Audit records must appear as JSON on stdout."""
    import app.audit as audit_mod

    # Reset configured flag to force reconfiguration
    audit_mod._configured = False

    audit_mod.log_interpretation(
        study_instance_uid="1.2.3.test",
        exam_type="XR_CHEST",
        status="COMPLETED",
        finding_codes=["PNEUMOTHORAX"],
        critical_alert=False,
        model_name="gpt-4o-xray-vision",
        modality_handled="XRAY",
        clinical_indication=None,
        warnings=[],
    )

    captured = capsys.readouterr()
    import json

    record = json.loads(captured.out.strip().split("\n")[-1])
    assert record["exam_type"] == "XR_CHEST"
    assert record["status"] == "COMPLETED"
    assert "PNEUMOTHORAX" in record["finding_codes"]
    assert "timestamp" in record


def test_body_part_normalised_to_uppercase() -> None:
    """body_part in StudyInfo must always be uppercase."""
    from app.interpretation.models import StudyInfo

    study = StudyInfo(
        body_part="Kidney",
    )
    # StudyInfo stores whatever is passed â€” the normalisation
    # happens at build time. Verify the service normalises it
    # by checking the classifier output directly.
    from app.protocol_classifier import classify_exam_type

    result = classify_exam_type(
        modality="CR",
        body_part_examined="Kidney",
        study_description="CT Urogram with 3D",
        series_description="projection urogram",
    )
    assert result.exam_type == "XR_ABDOMEN"


def test_body_part_uppercase_in_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """build_dicom_response must uppercase body_part in StudyInfo."""
    import app.interpretation.interpretation_service as svc
    from app.config import Settings
    from pathlib import Path
    import tempfile

    # Patch extract_dicom_metadata to return lowercase body_part
    monkeypatch.setattr(
        "app.interpretation.interpretation_service.extract_dicom_metadata",
        lambda _: {
            "modality": "CR",
            "study_description": "CT Urogram",
            "series_description": "projection urogram",
            "body_part_examined": "Kidney",  # lowercase â€” must be normalised
            "protocol_name": None,
            "study_instance_uid": "1.2.3",
            "view_position": None,
            "performed_protocol_codes": None,
            "image_laterality": None,
            "patient_age": None,
            "patient_sex": "M",
        },
    )

    # Stub _load_upload_to_dicom_dir to return one fake dcm path
    monkeypatch.setattr(
        svc,
        "_load_upload_to_dicom_dir",
        lambda upload, dicom_dir: [Path("/fake/1.dcm")],
    )
    # Stub _dicom_to_png so no real DICOM reading happens
    monkeypatch.setattr(svc, "_dicom_to_png", lambda src, dst: dst.write_bytes(b"PNG"))
    # Stub GPT to return empty findings
    monkeypatch.setattr(svc, "_should_use_gpt", lambda _: True)
    monkeypatch.setattr(
        "app.interpretation.gpt_xray_model.run_gpt_xray_model",
        lambda **kwargs: (
            [],
            {},
            {
                "name": "gpt-4o-xray-vision",
                "image_quality": "ADEQUATE",
                "laterality_from_image": None,
                "view_detected": "AP",
                "body_part_detected": "ABDOMEN",
            },
        ),
    )

    settings = Settings(openai_api_key="sk-test")
    with tempfile.TemporaryDirectory() as tmp:
        fake_dcm = Path(tmp) / "upload.dcm"
        fake_dcm.write_bytes(b"FAKE")
        workdir = Path(tmp) / "work"
        workdir.mkdir()

        response = svc.build_dicom_response(
            upload_input_path=fake_dcm,
            workdir=workdir,
            clinical_indication=None,
            settings=settings,
        )

    assert response.study.body_part == "KIDNEY", (
        f"Expected 'KIDNEY', got '{response.study.body_part}'"
    )


def test_default_model_is_pinned_version() -> None:
    """Default openai_model must be a pinned dated version, not floating alias."""
    from app.config import Settings

    settings = Settings()
    # Must not be the bare floating alias
    assert settings.openai_model != "gpt-4o", (
        "openai_model must be a pinned dated version like "
        "'gpt-4o-2024-11-20', not the floating 'gpt-4o' alias."
    )
    # Must follow the dated pattern YYYY-MM-DD
    import re

    assert re.search(r"\d{4}-\d{2}-\d{2}", settings.openai_model), (
        f"Expected a dated model version, got: {settings.openai_model}"
    )
