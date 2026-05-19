from __future__ import annotations

from app.interpretation.xray_model import STRONG_THRESHOLD, WEAK_THRESHOLD, build_findings_from_model_outputs


def _codes(findings) -> set[str]:
    return {f.finding_code for f in findings}


def test_prob_034_returns_no_finding() -> None:
    findings = build_findings_from_model_outputs({"Consolidation": 0.34})
    assert findings == []


def test_prob_040_returns_low_confidence_finding() -> None:
    findings = build_findings_from_model_outputs({"Lung Opacity": 0.40})
    codes = _codes(findings)
    assert "LUNG_OPACITY" in codes
    # Combined rule should also trigger at weak threshold when no strong opacity exists.
    assert "POSSIBLE_LUNG_OPACITY_OR_AIRSPACE_ABNORMALITY" in codes
    f = next(x for x in findings if x.finding_code == "LUNG_OPACITY")
    assert WEAK_THRESHOLD <= f.confidence < STRONG_THRESHOLD


def test_prob_070_returns_standard_finding_and_no_combined_dup() -> None:
    findings = build_findings_from_model_outputs({"Lung Opacity": 0.70})
    codes = _codes(findings)
    assert "LUNG_OPACITY" in codes
    # Avoid duplicate combined finding when strong opacity exists.
    assert "POSSIBLE_LUNG_OPACITY_OR_AIRSPACE_ABNORMALITY" not in codes
    f = next(x for x in findings if x.finding_code == "LUNG_OPACITY")
    assert f.confidence >= STRONG_THRESHOLD


def test_combined_lung_abnormality_triggers_for_consolidation_weak() -> None:
    findings = build_findings_from_model_outputs({"Consolidation": 0.36})
    codes = _codes(findings)
    assert "CONSOLIDATION" in codes
    assert "POSSIBLE_LUNG_OPACITY_OR_AIRSPACE_ABNORMALITY" in codes
