"""Seed the RAG store with code lookups for common diagnosis/procedure terms."""
import json
import logging
import os
from typing import Any, Dict

from app.core.config import settings
from app.ontology.hcpcs import HCPCSClient
from app.ontology.icd10 import ICD10Client
from app.rag.store import CodingRAGStore

logger = logging.getLogger(__name__)


def _load_seed_terms() -> Dict[str, Any]:
    """Read coding_seed_terms.json from the project root."""
    path = os.path.join(settings.project_dir, settings.seed_terms_file)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Seed terms file not found: {path}")
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def seed_rag_store(force: bool = False) -> int:
    """Populate the RAG store with codes for the seed terms.

    Args:
        force: When True, re-seed every term even if the store is already
            populated. When False (default), skip seeding if the store
            already has records.

    Returns:
        Number of records present in the store after the call.
    """
    store = CodingRAGStore()
    existing = store.count()
    if existing > 0 and not force:
        logger.info(
            "RAG store already contains %d records; skipping seed (use force=True to re-seed).",
            existing,
        )
        return existing

    seeds = _load_seed_terms()
    icd10 = ICD10Client()
    hcpcs = HCPCSClient()

    icd10_terms = seeds.get("icd10_terms", [])
    logger.info("Seeding RAG store with %d ICD-10-CM terms...", len(icd10_terms))
    for term in icd10_terms:
        try:
            hit = icd10.lookup(term)
            if hit and hit.get("code"):
                store.upsert(
                    term=term, code_system="ICD-10-CM",
                    code=hit["code"], display=hit.get("display"), source="seed",
                )
        except (RuntimeError, ValueError) as exc:
            logger.warning("ICD-10-CM lookup failed for '%s': %s", term, exc)

    hcpcs_terms = seeds.get("hcpcs_terms", [])
    logger.info("Seeding RAG store with %d HCPCS terms...", len(hcpcs_terms))
    for term in hcpcs_terms:
        try:
            hit = hcpcs.lookup(term)
            if hit and hit.get("code"):
                store.upsert(
                    term=term, code_system="HCPCS",
                    code=hit["code"], display=hit.get("display"), source="seed",
                )
        except (RuntimeError, ValueError) as exc:
            logger.warning("HCPCS lookup failed for '%s': %s", term, exc)

    cpt_terms = seeds.get("cpt_terms", [])
    logger.info("Seeding RAG store with %d curated CPT terms (no live API available)...", len(cpt_terms))
    for entry in cpt_terms:
        store.upsert(
            term=entry["display"], code_system="CPT",
            code=entry["code"], display=entry["display"], source="seed",
        )

    final_count = store.count()
    logger.info("RAG store seeded. Total records: %d", final_count)
    return final_count
