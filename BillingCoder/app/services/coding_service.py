"""Service layer orchestrating the CodingAssist 6-phase pipeline."""
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.ai.client import CodingAIClient
from app.ai.prompts import (
    build_draft_system_prompt,
    build_draft_user_prompt,
    build_extraction_system_prompt,
    build_extraction_user_prompt,
    build_normalize_system_prompt,
    build_normalize_user_prompt,
)
from app.core.config import settings
from app.ontology.hcpcs import HCPCSClient
from app.ontology.icd10 import ICD10Client
from app.rag.store import CodingRAGStore, get_rag_store
from app.rules.edit_engine import EditEngine

logger = logging.getLogger(__name__)


class CodingService:
    """Orchestrates the 6-phase charge-capture pipeline.

    Phases 2, 3, and 5 call the LLM. Phases 4 and 6 are pure deterministic
    Python: the rules engine, not the LLM, is authoritative for whether a
    code combination is compliant.
    """

    def __init__(self):
        """Construct collaborators and load static domain artifacts."""
        self.ai_client = CodingAIClient()
        self.project_dir = settings.project_dir
        self.rag: CodingRAGStore = get_rag_store()
        self.icd10 = ICD10Client()
        self.hcpcs = HCPCSClient()
        self.edit_engine = EditEngine()
        self._guide_text: Optional[str] = None
        self._schema_text: Optional[str] = None

    def _load_text_file(self, relative_path: str) -> str:
        """Read a file relative to project root. Raises FileNotFoundError."""
        filepath = os.path.join(self.project_dir, relative_path)
        if not os.path.isfile(filepath):
            raise FileNotFoundError(f"Required file not found: {relative_path}")
        with open(filepath, "r", encoding="utf-8") as fh:
            return fh.read()

    def _guide(self) -> str:
        """Lazy-load and cache the billing data guide."""
        if self._guide_text is None:
            self._guide_text = self._load_text_file(settings.billing_guide_file)
        return self._guide_text

    def _schema(self) -> str:
        """Lazy-load and cache the output schema."""
        if self._schema_text is None:
            self._schema_text = self._load_text_file(settings.output_schema_file)
        return self._schema_text

    def coding_edits_summary(self) -> Dict[str, Any]:
        """Return a summary of the loaded edit rules (no AI call)."""
        return self.edit_engine.summary()

    def generate_charge(
        self,
        encounter_metadata: Dict[str, Any],
        documents: List[Dict[str, Any]],
        upstream_entities: Optional[List[Dict[str, Any]]],
    ) -> Dict[str, Any]:
        """Run the full 6-phase pipeline and return the structured response."""
        logger.info("Pipeline start: encounter_id=%s", encounter_metadata.get("encounter_id"))

        normalized_notes = self._phase_2_normalize(documents)

        coded_entities = self._phase_3_extract_and_ground(normalized_notes, upstream_entities)

        compliance_flags = self._phase_4_compliance_check(coded_entities)

        draft = self._phase_5_draft(
            encounter_metadata=encounter_metadata,
            normalized_notes=normalized_notes,
            coded_entities=coded_entities,
            compliance_flags=compliance_flags,
        )

        enforced_draft, enforcement_flags = self._phase_6_enforce(draft, coded_entities)
        compliance_flags = compliance_flags + enforcement_flags

        generated_at = datetime.now(timezone.utc)
        timestamp_str = generated_at.strftime("%Y%m%d_%H%M%S")
        charge_id = f"{encounter_metadata.get('encounter_id', 'UNKNOWN')}-{timestamp_str}"

        response: Dict[str, Any] = {
            "charge_id": charge_id,
            "encounter_id": encounter_metadata.get("encounter_id"),
            "patient_id": encounter_metadata.get("patient_id"),
            "date_of_service": encounter_metadata.get("date_of_service"),
            "generated_at_utc": generated_at.isoformat(),
            "model_used": self.ai_client.model,
            "normalized_notes": normalized_notes,
            "coded_entities": coded_entities,
            "compliance_flags": compliance_flags,
            "charge_draft": enforced_draft,
        }

        output_file = self._save_output(charge_id, response)
        response["output_file"] = output_file

        logger.info(
            "Pipeline complete: charge_id=%s, entities=%d, flags=%d, lines=%d",
            charge_id, len(coded_entities), len(compliance_flags), len(enforced_draft["charge_lines"]),
        )
        return response

    def _phase_2_normalize(self, documents: List[Dict[str, Any]]) -> str:
        """Phase 2: LLM call #1 -- reconcile multiple source documents into one narrative."""
        logger.info("Phase 2 normalize (LLM call 1), %d source document(s)", len(documents))
        system = build_normalize_system_prompt(self._guide())
        user = build_normalize_user_prompt(documents)
        result = self.ai_client.analyze(system, user)
        normalized = result.get("normalized_notes")
        if not isinstance(normalized, str) or not normalized.strip():
            raise ValueError("Normalizer returned empty normalized_notes")
        return normalized

    def _phase_3_extract_and_ground(
        self,
        normalized_notes: str,
        upstream_entities: Optional[List[Dict[str, Any]]],
    ) -> List[Dict[str, Any]]:
        """Phase 3: LLM call #2 (entity extraction) + RAG/live ICD-10-CM/HCPCS grounding."""
        logger.info("Phase 3 extract entities (LLM call 2) + ground via RAG/live APIs")
        system = build_extraction_system_prompt()
        user = build_extraction_user_prompt(normalized_notes)
        result = self.ai_client.analyze(system, user)
        raw_entities = result.get("entities", [])
        if not isinstance(raw_entities, list):
            raise ValueError("Extractor returned non-list entities")

        grounded: List[Dict[str, Any]] = []
        seen_keys = set()

        for ent in upstream_entities or []:
            text = (ent.get("text") or "").strip()
            if not text:
                continue
            key = (text.lower(), "diagnosis")
            if key in seen_keys:
                continue
            seen_keys.add(key)
            grounded.append(self._ground_diagnosis(text=text, status="confirmed", laterality=ent.get("laterality")))

        for entity in raw_entities:
            text = (entity.get("text") or "").strip()
            if not text:
                continue
            kind = (entity.get("kind") or "").strip().lower()
            if kind not in {"diagnosis", "procedure"}:
                continue
            key = (text.lower(), kind)
            if key in seen_keys:
                continue
            seen_keys.add(key)

            if kind == "diagnosis":
                status = (entity.get("status") or "confirmed").strip().lower()
                if status not in {"confirmed", "suspected", "ruled_out"}:
                    status = "confirmed"
                grounded.append(self._ground_diagnosis(
                    text=text, status=status, laterality=entity.get("laterality"),
                ))
            else:
                grounded.append(self._ground_procedure(
                    text=text,
                    laterality=entity.get("laterality"),
                    units=entity.get("units") or 1,
                ))
        return grounded

    def _ground_diagnosis(self, text: str, status: str, laterality: Optional[str]) -> Dict[str, Any]:
        """Resolve a diagnosis surface form to an ICD-10-CM code via RAG first, live API second."""
        entry: Dict[str, Any] = {
            "text": text, "kind": "diagnosis", "status": status, "laterality": laterality,
            "units": None, "code_system": None, "code": None, "display": None, "source": "none",
        }

        rag_hit = self.rag.query(text, code_systems=["ICD-10-CM"])
        if rag_hit and rag_hit.get("code"):
            entry.update(code_system="ICD-10-CM", code=rag_hit["code"], display=rag_hit.get("display"), source="rag")
            return entry

        try:
            live = self.icd10.lookup(text)
            if live and live.get("code"):
                entry.update(
                    code_system="ICD-10-CM", code=live["code"],
                    display=live.get("display"), source="icd10_api",
                )
                self.rag.upsert(
                    term=text, code_system="ICD-10-CM",
                    code=live["code"], display=live.get("display"), source="runtime",
                )
        except (RuntimeError, ValueError) as exc:
            logger.warning("Live ICD-10-CM lookup failed for '%s': %s", text, exc)

        return entry

    def _ground_procedure(self, text: str, laterality: Optional[str], units: int) -> Dict[str, Any]:
        """Resolve a procedure surface form to a CPT/HCPCS code via RAG first, live HCPCS API second.

        CPT has no free public lookup API (AMA copyright), so a CPT miss in
        the RAG store falls back only to live HCPCS, never a live CPT call.
        """
        entry: Dict[str, Any] = {
            "text": text, "kind": "procedure", "status": "confirmed", "laterality": laterality,
            "units": units, "code_system": None, "code": None, "display": None, "source": "none",
        }

        rag_hit = self.rag.query(text, code_systems=["CPT", "HCPCS"])
        if rag_hit and rag_hit.get("code"):
            entry.update(
                code_system=rag_hit.get("code_system"), code=rag_hit["code"],
                display=rag_hit.get("display"), source="rag",
            )
            return entry

        try:
            live = self.hcpcs.lookup(text)
            if live and live.get("code"):
                entry.update(code_system="HCPCS", code=live["code"], display=live.get("display"), source="hcpcs_api")
                self.rag.upsert(
                    term=text, code_system="HCPCS",
                    code=live["code"], display=live.get("display"), source="runtime",
                )
        except (RuntimeError, ValueError) as exc:
            logger.warning("Live HCPCS lookup failed for '%s': %s", text, exc)

        return entry

    def _phase_4_compliance_check(self, coded_entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Phase 4: deterministic NCCI/MUE/medical-necessity/ruled-out checks."""
        logger.info("Phase 4 compliance check (deterministic)")
        procedures = [e for e in coded_entities if e["kind"] == "procedure" and e.get("code")]
        diagnoses = [e for e in coded_entities if e["kind"] == "diagnosis"]

        flags: List[Dict[str, Any]] = []
        flags.extend(self.edit_engine.check_ptp_edits([p["code"] for p in procedures]))
        flags.extend(self.edit_engine.check_mue(procedures))
        flags.extend(self.edit_engine.check_medical_necessity(procedures, diagnoses))
        flags.extend(self.edit_engine.check_ruled_out_diagnoses(diagnoses))
        return flags

    def _phase_5_draft(
        self,
        encounter_metadata: Dict[str, Any],
        normalized_notes: str,
        coded_entities: List[Dict[str, Any]],
        compliance_flags: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Phase 5: LLM call #3 -- template-constrained charge-ticket draft."""
        logger.info("Phase 5 draft (LLM call 3)")
        system = build_draft_system_prompt(self._guide(), self._schema())
        user = build_draft_user_prompt(
            encounter_metadata=encounter_metadata,
            normalized_notes=normalized_notes,
            coded_entities=coded_entities,
            compliance_flags=compliance_flags,
        )
        result = self.ai_client.analyze(system, user)
        if not isinstance(result.get("charge_lines"), list):
            raise ValueError("Drafter omitted required field: charge_lines")
        if not isinstance(result.get("claim_notes"), str):
            raise ValueError("Drafter omitted required field: claim_notes")
        return result

    def _phase_6_enforce(
        self, draft: Dict[str, Any], coded_entities: List[Dict[str, Any]],
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """Phase 6: deterministic enforcement of blocking compliance flags.

        The LLM's draft is advisory input here, not the final word: units are
        clamped to MUE ceilings, blocking-bundled column-2 codes are dropped
        in favor of the more comprehensive column-1 code, and any diagnosis
        link to a ruled-out code is stripped, regardless of what the LLM proposed.
        """
        logger.info("Phase 6 enforce (deterministic)")
        flags: List[Dict[str, Any]] = []
        mue_caps = {m["cpt"]: m["max_units_per_day"] for m in self.edit_engine.mue_limits()}
        ruled_out_codes = {
            e["code"] for e in coded_entities
            if e.get("kind") == "diagnosis" and e.get("status") == "ruled_out" and e.get("code")
        }

        lines = [dict(line) for line in draft.get("charge_lines", [])]

        for line in lines:
            code = line.get("code")
            units = line.get("units", 1) or 1
            cap = mue_caps.get(code)
            if cap is not None and units > cap:
                flags.append({
                    "rule_type": "mue",
                    "severity": "blocking",
                    "message": f"Units for {code} clamped from {units} to MUE cap {cap}.",
                    "affected_codes": [code],
                })
                line["units"] = cap

            line["linked_diagnosis_codes"] = [
                c for c in line.get("linked_diagnosis_codes", []) if c not in ruled_out_codes
            ]

        present_codes = {ln.get("code") for ln in lines}
        drop_codes = self.edit_engine.codes_to_drop(present_codes)
        final_lines = [ln for ln in lines if ln.get("code") not in drop_codes]
        for code in drop_codes:
            flags.append({
                "rule_type": "ptp_edit",
                "severity": "blocking",
                "message": (
                    f"{code} removed from the charge ticket: bundled into a "
                    "more comprehensive procedure billed in the same session."
                ),
                "affected_codes": [code],
            })

        return {"charge_lines": final_lines, "claim_notes": draft.get("claim_notes", "")}, flags

    def _save_output(self, charge_id: str, response: Dict[str, Any]) -> str:
        """Persist the full response to output/ with a timestamped filename."""
        output_dir = os.path.join(self.project_dir, "output")
        os.makedirs(output_dir, exist_ok=True)
        filename = f"{charge_id}.json"
        filepath = os.path.join(output_dir, filename)
        with open(filepath, "w", encoding="utf-8") as fh:
            json.dump(response, fh, indent=2)
        return filepath
