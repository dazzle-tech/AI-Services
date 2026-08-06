"""
Clinical Guidelines Service
Retrieves relevant medical guidelines, protocols, and treatment standards
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Keep LangChain telemetry quiet before any optional imports.
os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")
os.environ.setdefault("LANGCHAIN_ENDPOINT", "")


def _split_text(text: str, chunk_size: int = 800, chunk_overlap: int = 150) -> List[str]:
    """Simple character splitter — avoids importing langchain_text_splitters/transformers at startup."""
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    chunks: List[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = max(0, end - chunk_overlap)
    return chunks


def _load_pdf_pages(path: Path) -> List[Tuple[str, int]]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages: List[Tuple[str, int]] = []
    for i, page in enumerate(reader.pages):
        content = (page.extract_text() or "").strip()
        if content:
            pages.append((content, i + 1))
    return pages


class GuidelinesService:
    """Service for retrieving clinical guidelines using RAG."""

    def __init__(self):
        self.embeddings = None
        self.vectorstore = None
        self.initialized = False
        self.rag_available = True
        self.guidelines_dir = "data/guidelines"
        self.vector_store_path = "./vector_store_guidelines"
        self._Document = None

    # =========================
    # Initialization
    # =========================
    def initialize(self):
        if self.initialized:
            return

        try:
            from langchain_community.embeddings import HuggingFaceEmbeddings
            from langchain_community.vectorstores import Chroma
            from langchain.schema import Document
        except Exception as e:
            logger.warning("LangChain / RAG dependencies missing: %s", e)
            self.rag_available = False
            self.initialized = True
            return

        self._Document = Document
        self._Chroma = Chroma

        logger.info("Initializing Clinical Guidelines Assistant...")

        # This loads sentence-transformers/transformers once at init, not at process import.
        self.embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            model_kwargs={"device": "cpu"},
        )

        logger.info("Embeddings model loaded")
        self._load_guidelines()
        self.initialized = True
        logger.info("Clinical Guidelines system initialized")

    # =========================
    # Loading
    # =========================
    def _load_guidelines(self):
        os.makedirs(self.guidelines_dir, exist_ok=True)

        if os.path.exists(self.vector_store_path):
            logger.info("Loading existing vector store...")
            self.vectorstore = self._Chroma(
                embedding_function=self.embeddings,
                persist_directory=self.vector_store_path,
            )
            logger.info("Loaded existing guidelines database")
            return

        documents: List[Any] = []

        for file in Path(self.guidelines_dir).rglob("*"):
            suffix = file.suffix.lower()
            if suffix == ".pdf":
                for content, page in _load_pdf_pages(file):
                    documents.append(
                        self._Document(
                            page_content=content,
                            metadata={
                                "source_file": file.name,
                                "page": page,
                                "specialty": self._get_specialty_from_path(str(file)),
                            },
                        )
                    )
                logger.info("Loaded: %s", file.name)
            elif suffix == ".txt":
                content = file.read_text(encoding="utf-8", errors="ignore").strip()
                if content:
                    documents.append(
                        self._Document(
                            page_content=content,
                            metadata={
                                "source_file": file.name,
                                "page": "N/A",
                                "specialty": self._get_specialty_from_path(str(file)),
                            },
                        )
                    )
                logger.info("Loaded: %s", file.name)

        if not documents:
            self.vectorstore = self._Chroma(
                embedding_function=self.embeddings,
                persist_directory=self.vector_store_path,
            )
            return

        chunks: List[Any] = []
        for doc in documents:
            for piece in _split_text(doc.page_content):
                chunks.append(
                    self._Document(page_content=piece, metadata=dict(doc.metadata))
                )

        logger.info("Created %s text chunks", len(chunks))

        self.vectorstore = self._Chroma.from_documents(
            chunks,
            self.embeddings,
            persist_directory=self.vector_store_path,
        )

        logger.info(
            "Guidelines loaded: %s docs → %s chunks",
            len(documents),
            len(chunks),
        )

    # =========================
    # Specialty detection
    # =========================
    def _get_specialty_from_path(self, filepath: str) -> str:
        specialties = {
            "cardiology", "neurology", "surgery", "pediatrics",
            "oncology", "emergency", "general", "infectious",
            "pulmonary", "respiratory", "icu", "critical",
        }

        for part in Path(filepath).parts:
            if part.lower() in specialties:
                return part.lower()

        return "general"

    # =========================
    # Search
    # =========================
    def search_guidelines(
        self,
        query: str,
        k: int = 3,
        filter_specialty: Optional[str] = None,
    ) -> List[Dict]:

        if not self.vectorstore:
            return []

        try:
            if filter_specialty:
                results = self.vectorstore.similarity_search(
                    query,
                    k=k,
                    filter={"specialty": filter_specialty},
                )
                if not results:
                    results = self.vectorstore.similarity_search(query, k=k)
            else:
                results = self.vectorstore.similarity_search(query, k=k)

            return [
                {
                    "content": d.page_content,
                    "source": d.metadata.get("source_file"),
                    "page": d.metadata.get("page", "N/A"),
                    "specialty": d.metadata.get("specialty", "general"),
                }
                for d in results
            ]
        except Exception as e:
            logger.error("Search error: %s", e, exc_info=True)
            return []

    # =========================
    # Recommendations
    # =========================
    def get_protocol_recommendation(
        self,
        condition: str,
        patient_context: Optional[Dict] = None,
        specialty: Optional[str] = None,
    ) -> Tuple[str, List[Dict]]:

        if not self.initialized:
            self.initialize()

        query = f"{condition} treatment protocol guideline"

        if patient_context:
            if patient_context.get("age", 0) > 65:
                query += " elderly"
            if patient_context.get("conditions"):
                query += " " + " ".join(patient_context["conditions"])

        guidelines = self.search_guidelines(query, k=3, filter_specialty=specialty)

        if not guidelines:
            return f"No guidelines found for '{condition}'.", []

        text = f"📋 **Clinical Guidelines for: {condition}**\n\n"
        if patient_context:
            text += "**Patient Context:**\n"
            for k, v in patient_context.items():
                text += f"• {k}: {v}\n"
            text += "\n"

        text += "**Relevant Guidelines:**\n\n"

        for i, g in enumerate(guidelines, 1):
            text += f"**{i}. {g['source']}** [{g['specialty']}]\n"
            text += g["content"][:500].strip() + "\n\n---\n\n"

        return text, guidelines

    # =========================
    # Stats
    # =========================
    def get_statistics(self) -> Dict:
        if not self.vectorstore:
            return {"status": "empty"}

        files: Dict[str, List[str]] = {}
        for root, _, fs in os.walk(self.guidelines_dir):
            for f in fs:
                if f.endswith((".pdf", ".txt")):
                    spec = self._get_specialty_from_path(os.path.join(root, f))
                    files.setdefault(spec, []).append(f)

        return {
            "status": "active",
            "total_documents": sum(len(v) for v in files.values()),
            "specialties": list(files.keys()),
            "by_specialty": {k: len(v) for k, v in files.items()},
        }


guidelines_service = GuidelinesService()
