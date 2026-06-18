"""Local RAG store for ICD-10-CM codes and RadLex terms.

Two retrieval modes:

1. **Embeddings mode** (preferred). If `rag_data/embeddings.npz` is present,
   the user query is embedded with OpenAI and ranked by cosine similarity
   against the pre-embedded term corpus.
2. **Keyword fallback**. If no embeddings file exists (fresh checkout,
   offline test environment), retrieval falls back to substring/synonym
   matching. This keeps the service runnable and testable without making
   any OpenAI calls during ingestion.

Run `python -m app.services.rag_store ingest` once to build the embeddings
file. The file path is configured via RAG_EMBEDDINGS_FILE in .env.
"""
import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from app.core.config import settings

logger = logging.getLogger(__name__)


def _project_path(relative: str) -> str:
    """Resolve a path relative to the project root."""
    return os.path.join(settings.project_dir, relative)


def _load_terms(filepath: str) -> List[Dict[str, Any]]:
    """Load a JSON term file from disk."""
    if not os.path.isfile(filepath):
        raise FileNotFoundError(f"RAG term file not found: {filepath}")
    with open(filepath, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _searchable_text(entry: Dict[str, Any]) -> str:
    """Concatenate term + synonyms into a single string for embedding/matching."""
    parts = [entry.get("term", "")] + list(entry.get("synonyms", []) or [])
    return " | ".join(p for p in parts if p)


class RagStore:
    """Singleton-ish retrieval store across ICD-10 and RadLex term sets."""

    def __init__(self) -> None:
        self.icd10: List[Dict[str, Any]] = _load_terms(_project_path(settings.icd10_file))
        self.radlex: List[Dict[str, Any]] = _load_terms(_project_path(settings.radlex_file))
        self._embeddings: Optional[Dict[str, np.ndarray]] = None
        self._load_embeddings_if_present()

    def _load_embeddings_if_present(self) -> None:
        """Load pre-computed embeddings if the .npz file exists."""
        path = _project_path(settings.rag_embeddings_file)
        if not os.path.isfile(path):
            logger.info("No embeddings file at %s; using keyword fallback retrieval.", path)
            self._embeddings = None
            return
        try:
            data = np.load(path)
            self._embeddings = {"icd10": data["icd10"], "radlex": data["radlex"]}
            logger.info(
                "Loaded RAG embeddings: icd10=%s radlex=%s",
                self._embeddings["icd10"].shape,
                self._embeddings["radlex"].shape,
            )
        except (KeyError, ValueError, OSError) as exc:
            logger.warning("Failed to load embeddings file %s: %s. Falling back to keyword mode.", path, exc)
            self._embeddings = None

    def embeddings_present(self) -> bool:
        """Return True if vector retrieval is enabled."""
        return self._embeddings is not None

    # ---------- Retrieval ----------

    def retrieve_icd10(self, query: str, k: int = 5) -> List[Dict[str, Any]]:
        """Return top-k ICD-10 candidates with a `matched_phrase` annotation."""
        return self._retrieve(query, self.icd10, "icd10", k)

    def retrieve_radlex(self, query: str, k: int = 5) -> List[Dict[str, Any]]:
        """Return top-k RadLex candidates with a `matched_phrase` annotation."""
        return self._retrieve(query, self.radlex, "radlex", k)

    def _retrieve(
        self, query: str, corpus: List[Dict[str, Any]], corpus_key: str, k: int
    ) -> List[Dict[str, Any]]:
        """Dispatch to embeddings or keyword retrieval depending on availability."""
        if not query or not query.strip():
            return []
        if self._embeddings is not None:
            return self._retrieve_embeddings(query, corpus, corpus_key, k)
        return self._retrieve_keyword(query, corpus, k)

    def _retrieve_embeddings(
        self, query: str, corpus: List[Dict[str, Any]], corpus_key: str, k: int
    ) -> List[Dict[str, Any]]:
        """Vector retrieval using OpenAI embeddings + cosine similarity."""
        from openai import OpenAI

        client = OpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url or None,
            timeout=settings.openai_timeout,
        )
        response = client.embeddings.create(model=settings.openai_embed_model, input=query)
        q_vec = np.array(response.data[0].embedding, dtype=np.float32)
        q_vec = q_vec / (np.linalg.norm(q_vec) + 1e-12)

        corpus_vecs = self._embeddings[corpus_key]
        sims = corpus_vecs @ q_vec
        top_idx = np.argsort(-sims)[:k]
        out: List[Dict[str, Any]] = []
        for i in top_idx:
            entry = dict(corpus[int(i)])
            entry["matched_phrase"] = query
            entry["_score"] = float(sims[i])
            out.append(entry)
        return out

    def _retrieve_keyword(
        self, query: str, corpus: List[Dict[str, Any]], k: int
    ) -> List[Dict[str, Any]]:
        """Substring + synonym match scored by overlap length."""
        q_lower = query.lower()
        scored: List[Tuple[int, Dict[str, Any], str]] = []
        for entry in corpus:
            best_match = ""
            candidates = [entry.get("term", "")] + list(entry.get("synonyms", []) or [])
            for cand in candidates:
                if not cand:
                    continue
                c_lower = cand.lower()
                if c_lower in q_lower or q_lower in c_lower:
                    if len(cand) > len(best_match):
                        best_match = cand
            if best_match:
                scored.append((len(best_match), entry, best_match))
        scored.sort(key=lambda t: -t[0])
        out: List[Dict[str, Any]] = []
        for _, entry, matched in scored[:k]:
            row = dict(entry)
            row["matched_phrase"] = matched
            out.append(row)
        return out


# ---------- Ingestion script ----------


def build_embeddings() -> None:
    """Embed every ICD-10 and RadLex entry and save to disk as .npz."""
    from openai import OpenAI

    logger.info("Starting RAG embedding ingestion.")
    icd10 = _load_terms(_project_path(settings.icd10_file))
    radlex = _load_terms(_project_path(settings.radlex_file))
    icd10_texts = [_searchable_text(e) for e in icd10]
    radlex_texts = [_searchable_text(e) for e in radlex]

    client = OpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url or None,
        timeout=settings.openai_timeout,
    )

    def _embed_batch(texts: List[str]) -> np.ndarray:
        """Embed a list of strings; return an L2-normalized matrix."""
        response = client.embeddings.create(model=settings.openai_embed_model, input=texts)
        vecs = np.array([d.embedding for d in response.data], dtype=np.float32)
        norms = np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-12
        return vecs / norms

    icd10_vecs = _embed_batch(icd10_texts)
    radlex_vecs = _embed_batch(radlex_texts)

    out_path = _project_path(settings.rag_embeddings_file)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    np.savez(out_path, icd10=icd10_vecs, radlex=radlex_vecs)
    logger.info(
        "Wrote embeddings: %s (icd10=%d, radlex=%d)", out_path, len(icd10_vecs), len(radlex_vecs)
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    if len(sys.argv) > 1 and sys.argv[1] == "ingest":
        build_embeddings()
    else:
        print("Usage: python -m app.services.rag_store ingest")
        sys.exit(1)
