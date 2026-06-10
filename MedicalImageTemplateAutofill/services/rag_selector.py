"""
RAG-based template selection layer.

Uses ChromaDB with sentence-transformer embeddings to find the most relevant
radiology template for a given clinician input.
"""

import logging
from typing import Any, Optional

from models.schemas import Template, TemplateCandidate
from services.template_repository import TemplateRepository
from services.modality_filter import allowed_modalities_for_context

logger = logging.getLogger(__name__)


class RAGTemplateSelector:
    COLLECTION_NAME = "radiology_templates"

    def __init__(
        self,
        repository: TemplateRepository,
        vector_store_path: str,
        embedding_model: str,
    ):
        self.repository = repository
        self.vector_store_path = vector_store_path
        self.embedding_model_name = embedding_model
        self._client: Optional[Any] = None
        self._collection: Optional[Any] = None
        self._embedding_fn: Optional[Any] = None
        self.initialized = False

    def initialize(self) -> None:
        if self.initialized:
            return

        logger.info("Initializing RAG selector (embedding model: %s)", self.embedding_model_name)

        # ChromaDB <=0.4.x imports `np.float_`, which NumPy removed from the public
        # namespace starting in 2.0. Patch the alias for compatibility so the
        # import succeeds on modern Python/NumPy stacks (e.g. Python 3.13).
        import numpy as np

        if not hasattr(np, "float_"):
            setattr(np, "float_", np.float64)
        if not hasattr(np, "unicode_"):
            setattr(np, "unicode_", np.str_)
        if not hasattr(np, "string_"):
            setattr(np, "string_", np.bytes_)

        try:
            import chromadb
            from chromadb.utils import embedding_functions
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "Failed to import ChromaDB. Ensure `chromadb` is installed and compatible "
                "with your Python/NumPy versions."
            ) from exc

        self._embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=self.embedding_model_name
        )
        self._client = chromadb.PersistentClient(path=self.vector_store_path)

        # Drop and rebuild collection to keep embeddings in sync with on-disk templates.
        try:
            self._client.delete_collection(self.COLLECTION_NAME)
        except Exception:
            pass

        self._collection = self._client.create_collection(
            name=self.COLLECTION_NAME,
            embedding_function=self._embedding_fn,
            metadata={"hnsw:space": "cosine"},
        )

        templates = self.repository.all()
        if not templates:
            logger.warning("No templates available to index")
            self.initialized = True
            return

        documents = [self._template_to_document(t) for t in templates]
        metadatas = [
            {
                "template_id": t.template_id,
                "name": t.name,
                "modality": t.modality,
                "body_region": t.body_region or "",
            }
            for t in templates
        ]
        ids = [t.template_id for t in templates]

        self._collection.add(documents=documents, metadatas=metadatas, ids=ids)
        logger.info("Indexed %d templates into the vector store", len(templates))
        self.initialized = True

    @staticmethod
    def _template_to_document(template: Template) -> str:
        parts = [
            template.name,
            f"Modality: {template.modality}",
            f"Body region: {template.body_region or 'N/A'}",
            template.description,
            "Keywords: " + ", ".join(template.keywords),
        ]
        return "\n".join(parts)

    @staticmethod
    def derive_intent_profile(input_data: str) -> str:
        """Lightweight intent string built from the raw input — used as the
        RAG search query. Keeps things prototype-simple (no extra LLM call)."""
        snippet = input_data.strip().replace("\n", " ")
        return snippet[:512]

    def select(
        self,
        input_data: str,
        top_k: int = 3,
        patient_context: dict | None = None,
        output_language: str = "el",
    ) -> list[TemplateCandidate]:
        if not self.initialized:
            self.initialize()
        if self._collection is None:
            return []

        query = self.derive_intent_profile(input_data)
        ctx = patient_context or {}
        mod = ctx.get("modality_filter") or ctx.get("Modality") or ctx.get("modality")
        allowed = allowed_modalities_for_context(mod)

        # Query a larger pool so modality filtering doesn't return an empty list.
        n_results = max(top_k, top_k * 8)
        results = self._collection.query(query_texts=[query], n_results=n_results)

        candidates: list[TemplateCandidate] = []
        ids = results.get("ids", [[]])[0]
        distances = results.get("distances", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]

        for template_id, distance, metadata in zip(ids, distances, metadatas):
            # Cosine distance in [0, 2] → similarity in [-1, 1]; clamp for display.
            similarity = max(0.0, 1.0 - float(distance))
            cand_mod = (metadata.get("modality", "") or "").strip().upper()
            if allowed and cand_mod not in allowed:
                continue
            template = self.repository.get(template_id)
            localized_name = (
                self.repository.get_localized_template_name(template, output_language)
                if template is not None
                else metadata.get("name", template_id)
            )
            candidates.append(
                TemplateCandidate(
                    template_id=template_id,
                    name=localized_name,
                    modality=metadata.get("modality", ""),
                    body_region=metadata.get("body_region") or None,
                    score=round(similarity, 4),
                )
            )

        # Ensure we return at most top_k after filtering.
        candidates = candidates[:top_k]

        if allowed and not candidates:
            xr = self.repository.get("xr_chest_2views")
            if xr is not None:
                candidates = [
                    TemplateCandidate(
                        template_id=xr.template_id,
                        name=self.repository.get_localized_template_name(xr, output_language),
                        modality=xr.modality,
                        body_region=xr.body_region,
                        score=1.0,
                    )
                ]

        return candidates
