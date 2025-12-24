"""
Clinical Guidelines Service
Retrieves relevant medical guidelines, protocols, and treatment standards
"""

import os
from typing import List, Dict, Optional, Tuple
from pathlib import Path


# =========================
# LangChain imports
# =========================
try:
    from langchain_community.embeddings import HuggingFaceEmbeddings
    from langchain_community.vectorstores import Chroma
    from langchain_community.document_loaders.pdf import PyPDFLoader
    from langchain_community.document_loaders.text import TextLoader
    from langchain.text_splitter import RecursiveCharacterTextSplitter
    from langchain.schema import Document

    # Disable noisy telemetry
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    os.environ["LANGCHAIN_ENDPOINT"] = ""

    RAG_AVAILABLE = True
except Exception as e:
    print("⚠️  LangChain dependencies missing:", e)
    RAG_AVAILABLE = False


class GuidelinesService:
    """Service for retrieving clinical guidelines using RAG."""

    def __init__(self):
        self.embeddings = None
        self.vectorstore = None
        self.initialized = False
        self.rag_available = RAG_AVAILABLE
        self.guidelines_dir = "data/guidelines"
        self.vector_store_path = "./vector_store_guidelines"

    # =========================
    # Initialization
    # =========================
    def initialize(self):
        if self.initialized:
            return

        if not self.rag_available:
            self.initialized = True
            return

        print("🏥 Initializing Clinical Guidelines Assistant...")

        self.embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            model_kwargs={"device": "cpu"}
        )

        print("✅ Embeddings model loaded")
        self._load_guidelines()
        self.initialized = True
        print("✅ Clinical Guidelines system initialized")

    # =========================
    # Loading
    # =========================
    def _load_guidelines(self):
        os.makedirs(self.guidelines_dir, exist_ok=True)

        if os.path.exists(self.vector_store_path):
            print("📚 Loading existing vector store...")
            self.vectorstore = Chroma(
                embedding_function=self.embeddings,
                persist_directory=self.vector_store_path
            )
            print("✅ Loaded existing guidelines database")
            return

        documents: List[Document] = []

        for file in Path(self.guidelines_dir).rglob("*"):
            if file.suffix.lower() == ".pdf":
                loader = PyPDFLoader(str(file))
            elif file.suffix.lower() == ".txt":
                loader = TextLoader(str(file))
            else:
                continue

            docs = loader.load()
            for doc in docs:
                doc.metadata["source_file"] = file.name
                doc.metadata["specialty"] = self._get_specialty_from_path(str(file))
            documents.extend(docs)
            print(f"   ✅ Loaded: {file.name}")

        if not documents:
            self.vectorstore = Chroma(
                embedding_function=self.embeddings,
                persist_directory=self.vector_store_path
            )
            return

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=800,
            chunk_overlap=150
        )

        chunks = splitter.split_documents(documents)
        print(f"✂️  Created {len(chunks)} text chunks")

        self.vectorstore = Chroma.from_documents(
            chunks,
            self.embeddings,
            persist_directory=self.vector_store_path
        )

        print(f"✅ Guidelines loaded: {len(documents)} docs → {len(chunks)} chunks")

    # =========================
    # Specialty detection
    # =========================
    def _get_specialty_from_path(self, filepath: str) -> str:
        specialties = {
            "cardiology", "neurology", "surgery", "pediatrics",
            "oncology", "emergency", "general", "infectious",
            "pulmonary", "respiratory", "icu", "critical"
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
        filter_specialty: Optional[str] = None
    ) -> List[Dict]:

        if not self.vectorstore:
            return []

        try:
            if filter_specialty:
                results = self.vectorstore.similarity_search(
                    query,
                    k=k,
                    filter={"specialty": filter_specialty}
                )
                if not results:
                    # 🔁 fallback if specialty too strict
                    results = self.vectorstore.similarity_search(query, k=k)
            else:
                results = self.vectorstore.similarity_search(query, k=k)

            return [
                {
                    "content": d.page_content,
                    "source": d.metadata.get("source_file"),
                    "page": d.metadata.get("page", "N/A"),
                    "specialty": d.metadata.get("specialty", "general")
                }
                for d in results
            ]
        except Exception as e:
            print("Search error:", e)
            return []

    # =========================
    # Recommendations
    # =========================
    def get_protocol_recommendation(
        self,
        condition: str,
        patient_context: Optional[Dict] = None,
        specialty: Optional[str] = None
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

        files = {}
        for root, _, fs in os.walk(self.guidelines_dir):
            for f in fs:
                if f.endswith((".pdf", ".txt")):
                    spec = self._get_specialty_from_path(os.path.join(root, f))
                    files.setdefault(spec, []).append(f)

        return {
            "status": "active",
            "total_documents": sum(len(v) for v in files.values()),
            "specialties": list(files.keys()),
            "by_specialty": {k: len(v) for k, v in files.items()}
        }


guidelines_service = GuidelinesService()
