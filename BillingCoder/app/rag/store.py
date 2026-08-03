"""ChromaDB-backed RAG store for billing code terms (ICD-10-CM, CPT, HCPCS)."""
import logging
import os
from typing import Any, Dict, List, Optional

import chromadb
from chromadb.config import Settings as ChromaSettings
from openai import OpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)


class CodingRAGStore:
    """Persistent local vector store of code-system-grounded billing terms.

    Each record stores a surface form (e.g. "laparoscopic appendectomy")
    plus its resolved code system, code, and display label as metadata.
    Queries return the top match within an optional set of code systems
    along with its code, so a diagnosis lookup never accidentally returns
    a procedure code and vice versa.
    """

    def __init__(self):
        """Initialize Chroma client, OpenAI embedding client, and collection."""
        persist_path = os.path.join(settings.project_dir, settings.rag_persist_dir)
        os.makedirs(persist_path, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=persist_path,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=settings.rag_collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        self._openai = OpenAI(
            api_key=settings.openai_api_key,
            timeout=settings.openai_timeout,
        )
        self._embedding_model = settings.openai_embedding_model
        self._top_k = settings.rag_top_k
        self._similarity_threshold = settings.rag_similarity_threshold

    def count(self) -> int:
        """Return the number of records currently in the store."""
        return self._collection.count()

    def _embed(self, texts: List[str]) -> List[List[float]]:
        """Return OpenAI embeddings for the given texts."""
        response = self._openai.embeddings.create(
            model=self._embedding_model,
            input=texts,
        )
        return [item.embedding for item in response.data]

    def upsert(self, term: str, code_system: str, code: str, display: Optional[str], source: str) -> None:
        """Add or update a billing-code record for the given surface form.

        Args:
            term: The surface form (canonical or alias).
            code_system: "ICD-10-CM" | "CPT" | "HCPCS".
            code: The resolved code.
            display: The canonical display label, if known.
            source: Where the code was resolved from (icd10_api, hcpcs_api, seed).
        """
        record_id = f"{term.strip().lower()}|{code_system}|{source}"
        metadata = {
            "term": term,
            "code_system": code_system,
            "code": code or "",
            "display": display or "",
            "source": source,
        }
        embedding = self._embed([term])[0]
        self._collection.upsert(
            ids=[record_id],
            embeddings=[embedding],
            documents=[term],
            metadatas=[metadata],
        )
        logger.info("RAG upserted term: %s (%s %s, source=%s)", term, code_system, code, source)

    def query(self, term: str, code_systems: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        """Return the top match for the term if its similarity passes the threshold.

        Args:
            term: Surface form to look up.
            code_systems: Restrict the search to these code systems (e.g.
                ["ICD-10-CM"] for diagnoses, ["CPT", "HCPCS"] for procedures).
                When None, search all code systems.

        Returns None when the store is empty or no record exceeds the
        similarity threshold; the caller is expected to fall back to the
        live ontology API in that case.
        """
        if self.count() == 0:
            return None
        embedding = self._embed([term])[0]
        where = {"code_system": {"$in": code_systems}} if code_systems else None
        result = self._collection.query(
            query_embeddings=[embedding],
            n_results=self._top_k,
            where=where,
        )
        if not result.get("ids") or not result["ids"][0]:
            return None
        best_distance = result["distances"][0][0]
        similarity = 1.0 - best_distance
        if similarity < self._similarity_threshold:
            return None
        metadata = result["metadatas"][0][0]
        return {
            "term": metadata.get("term"),
            "code_system": metadata.get("code_system"),
            "code": metadata.get("code") or None,
            "display": metadata.get("display") or None,
            "source": "rag",
            "similarity": similarity,
        }


_store_singleton: Optional[CodingRAGStore] = None


def get_rag_store() -> CodingRAGStore:
    """Return the singleton RAG store, creating it on first call."""
    global _store_singleton
    if _store_singleton is None:
        _store_singleton = CodingRAGStore()
    return _store_singleton
