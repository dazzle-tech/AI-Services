"""Deterministic compliance rules engine.

Loads coding_edit_rules.json (NCCI procedure-to-procedure bundling edits and
Medically Unlikely Edit unit ceilings) and medical_necessity_policies.json
(illustrative LCD-style covered-indication lists), and checks coded entities
against them. This engine -- never the LLM -- is authoritative for whether a
code combination is compliant; see billing_data_guide.txt section 5.
"""
import json
import logging
import os
from typing import Any, Dict, List, Set

from app.core.config import settings

logger = logging.getLogger(__name__)


class EditEngine:
    """Deterministic NCCI/MUE/medical-necessity checker."""

    def __init__(self):
        """Load the edit-rules and medical-necessity policy files."""
        self._rules = self._load_json(settings.coding_edit_rules_file)
        self._necessity = self._load_json(settings.medical_necessity_file)

    def _load_json(self, relative_path: str) -> Dict[str, Any]:
        """Read a JSON file relative to project root. Raises FileNotFoundError."""
        path = os.path.join(settings.project_dir, relative_path)
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Required file not found: {relative_path}")
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)

    def mue_limits(self) -> List[Dict[str, Any]]:
        """Return the configured MUE limit entries."""
        return self._rules.get("mue_limits", [])

    def ptp_edits(self) -> List[Dict[str, Any]]:
        """Return the configured PTP edit entries."""
        return self._rules.get("ptp_edits", [])

    def summary(self) -> Dict[str, Any]:
        """Return a summary of the loaded edit rules (no AI call)."""
        return {
            "ptp_edit_count": len(self.ptp_edits()),
            "mue_rule_count": len(self.mue_limits()),
            "ptp_edits": self.ptp_edits(),
            "mue_limits": self.mue_limits(),
        }

    def check_ptp_edits(self, cpt_codes: List[str]) -> List[Dict[str, Any]]:
        """Flag any NCCI procedure-to-procedure bundling conflicts.

        Severity is 'blocking' when modifier_indicator is '0' (no modifier
        can ever bypass the edit) and 'warning' when '1' (a modifier may
        apply if clinically supported).
        """
        codes = {c for c in cpt_codes if c}
        flags: List[Dict[str, Any]] = []
        for edit in self.ptp_edits():
            c1, c2 = edit["column1_cpt"], edit["column2_cpt"]
            if c1 in codes and c2 in codes:
                severity = "blocking" if edit.get("modifier_indicator") == "0" else "warning"
                flags.append({
                    "rule_type": "ptp_edit",
                    "severity": severity,
                    "message": (
                        f"{c2} ({edit.get('column2_desc')}) is NCCI-bundled into "
                        f"{c1} ({edit.get('column1_desc')}). {edit.get('rationale', '')}"
                    ).strip(),
                    "affected_codes": [c1, c2],
                })
        return flags

    def check_mue(self, procedures: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Flag any procedure whose total documented units exceed its MUE ceiling."""
        caps = {m["cpt"]: m["max_units_per_day"] for m in self.mue_limits()}
        totals: Dict[str, int] = {}
        for proc in procedures:
            code = proc.get("code")
            if not code:
                continue
            totals[code] = totals.get(code, 0) + (proc.get("units") or 1)

        flags: List[Dict[str, Any]] = []
        for code, total in totals.items():
            cap = caps.get(code)
            if cap is not None and total > cap:
                flags.append({
                    "rule_type": "mue",
                    "severity": "blocking",
                    "message": (
                        f"{code} documented {total} unit(s) for this date of "
                        f"service; Medically Unlikely Edit ceiling is {cap}."
                    ),
                    "affected_codes": [code],
                })
        return flags

    def check_medical_necessity(
        self, procedures: List[Dict[str, Any]], diagnoses: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Flag any procedure with no confirmed diagnosis matching its covered indications."""
        policies = {p["cpt"]: p for p in self._necessity.get("policies", [])}
        confirmed_dx_texts = {
            (d.get("text") or "").lower() for d in diagnoses if d.get("status") == "confirmed"
        }

        flags: List[Dict[str, Any]] = []
        for proc in procedures:
            code = proc.get("code")
            policy = policies.get(code)
            if not policy:
                continue
            covered = [c.lower() for c in policy.get("covered_indications", [])]
            if not any(c in dx or dx in c for dx in confirmed_dx_texts for c in covered):
                flags.append({
                    "rule_type": "medical_necessity",
                    "severity": "warning",
                    "message": (
                        f"No confirmed diagnosis on this encounter matches a covered "
                        f"indication for {code} ({policy.get('description')}). "
                        f"{policy.get('necessity_note', '')}"
                    ).strip(),
                    "affected_codes": [code],
                })
        return flags

    def check_ruled_out_diagnoses(self, diagnoses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Flag any diagnosis explicitly ruled out in the documentation."""
        flags: List[Dict[str, Any]] = []
        for dx in diagnoses:
            if dx.get("status") == "ruled_out":
                flags.append({
                    "rule_type": "ruled_out_diagnosis",
                    "severity": "blocking",
                    "message": (
                        f"'{dx.get('text')}' was explicitly ruled out in the "
                        "documentation and must not be billed as a confirmed diagnosis."
                    ),
                    "affected_codes": [dx["code"]] if dx.get("code") else [],
                })
        return flags

    def codes_to_drop(self, present_cpt_codes: Set[str]) -> Set[str]:
        """Return the set of column-2 codes that must be dropped from the draft.

        Applies only to blocking (modifier_indicator == '0') edits where both
        codes in the pair are present; the more comprehensive column-1 code
        is kept and the bundled column-2 code is dropped.
        """
        drop: Set[str] = set()
        for edit in self.ptp_edits():
            if edit.get("modifier_indicator") != "0":
                continue
            c1, c2 = edit["column1_cpt"], edit["column2_cpt"]
            if c1 in present_cpt_codes and c2 in present_cpt_codes:
                drop.add(c2)
        return drop
