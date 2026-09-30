"""Backend-owned, retrieval-only access to the confidential policy index.

This module deliberately contains no offer, booking, decision, or workflow
logic.  Future orchestration code can depend on ``PolicyRAGService`` without
knowing about ChromaDB's response format.
"""

from __future__ import annotations

import logging
import hashlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import chromadb
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer

from backend.app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class RAGError(RuntimeError):
    """Controlled base error for unavailable or invalid RAG operations."""


class RAGValidationError(RAGError):
    """Raised when a retrieval request cannot be safely processed."""


@dataclass(frozen=True)
class PolicyChunk:
    chunk_id: str
    text: str
    metadata: dict[str, str | int]


@dataclass(frozen=True)
class IngestionReport:
    document_name: str
    page_count: int
    chunk_count: int
    collection: str
    inserted_or_updated: int


@lru_cache(maxsize=2)
def _embedding_model(model_name: str) -> SentenceTransformer:
    """Load a real local/SentenceTransformers model once per model name."""

    try:
        # The approved model is cached during environment setup.  Loading from
        # that cache avoids a network metadata request on every API worker and
        # makes failures explicit if the real model was not provisioned.
        return SentenceTransformer(model_name, local_files_only=True)
    except Exception as exc:  # pragma: no cover - exercised by runtime configuration
        raise RAGError("Policy embedding model could not be loaded") from exc


class PolicyIngestionService:
    """Extract, chunk, embed and upsert the trusted policy document."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def policy_path(self) -> Path:
        return Path(self.settings.rag_policy_document_path)

    def extract_pages(self) -> list[str]:
        path = self.policy_path
        if not path.is_file():
            raise RAGError("Configured policy document is unavailable")
        try:
            reader = PdfReader(str(path))
            pages = [" ".join((page.extract_text() or "").split()) for page in reader.pages]
        except Exception as exc:
            raise RAGError("Configured policy document could not be read") from exc
        if not pages or not any(pages):
            raise RAGError("Configured policy document contains no extractable text")
        return pages

    def chunks_from_pages(self, pages: list[str]) -> list[PolicyChunk]:
        size = self.settings.rag_chunk_size
        overlap = self.settings.rag_chunk_overlap
        if size <= 0 or overlap < 0 or overlap >= size:
            raise RAGError("Invalid RAG chunk configuration")

        document_name = self.policy_path.name
        stem = "-".join(part.lower() for part in self.policy_path.stem.replace("_", "-").split("-") if part)
        chunks: list[PolicyChunk] = []
        for page_number, text in enumerate(pages, start=1):
            if not text:
                continue
            start = 0
            chunk_index = 0
            while start < len(text):
                body = text[start : start + size].strip()
                if body:
                    chunk_id = f"{stem}-p{page_number}-c{chunk_index}"
                    metadata: dict[str, str | int] = {
                        "document_name": document_name,
                        "page": page_number,
                        "chunk_index": chunk_index,
                        "chunk_id": chunk_id,
                    }
                    chunks.append(PolicyChunk(chunk_id=chunk_id, text=body, metadata=metadata))
                    chunk_index += 1
                if start + size >= len(text):
                    break
                start += size - overlap
        if not chunks:
            raise RAGError("Configured policy document produced no chunks")
        return chunks

    def _client(self):
        try:
            Path(self.settings.rag_persist_directory).mkdir(parents=True, exist_ok=True)
            return chromadb.PersistentClient(path=str(Path(self.settings.rag_persist_directory)))
        except Exception as exc:
            raise RAGError("Policy vector store could not be initialized") from exc

    def ingest_policy(self) -> IngestionReport:
        if not self.settings.rag_enabled:
            raise RAGError("Policy retrieval is disabled")
        pages = self.extract_pages()
        chunks = self.chunks_from_pages(pages)
        logger.info("Starting policy ingestion: document=%s pages=%d chunks=%d collection=%s", self.policy_path.name, len(pages), len(chunks), self.settings.rag_collection_name)
        try:
            collection = self._client().get_or_create_collection(
                name=self.settings.rag_collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            fingerprint = hashlib.sha256(self.policy_path.read_bytes() + repr((self.settings.rag_embedding_model, self.settings.rag_chunk_size, self.settings.rag_chunk_overlap, "normalized-v2")).encode()).hexdigest()
            if (collection.metadata or {}).get("fingerprint") == fingerprint and collection.count() == len(chunks):
                return IngestionReport(self.policy_path.name, len(pages), len(chunks), self.settings.rag_collection_name, 0)
            model = _embedding_model(self.settings.rag_embedding_model)
            embeddings = model.encode([chunk.text for chunk in chunks], normalize_embeddings=True).tolist()
            # Stable IDs + upsert make re-ingestion non-destructive and idempotent.
            collection.upsert(
                ids=[chunk.chunk_id for chunk in chunks],
                documents=[chunk.text for chunk in chunks],
                metadatas=[chunk.metadata for chunk in chunks],
                embeddings=embeddings,
            )
            stale = set(collection.get()["ids"]) - {chunk.chunk_id for chunk in chunks}
            if stale:
                collection.delete(ids=sorted(stale))
            collection.modify(metadata={"fingerprint": fingerprint})
        except RAGError:
            raise
        except Exception as exc:
            raise RAGError("Policy ingestion failed") from exc
        logger.info("Completed policy ingestion: document=%s chunks=%d collection=%s", self.policy_path.name, len(chunks), self.settings.rag_collection_name)
        return IngestionReport(
            document_name=self.policy_path.name,
            page_count=len(pages),
            chunk_count=len(chunks),
            collection=self.settings.rag_collection_name,
            inserted_or_updated=len(chunks),
        )


class PolicyRAGService:
    """The reusable application-level policy-retrieval interface."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def retrieve_policy(self, query: str, top_k: int | None = None) -> list[dict[str, str | int | float | None]]:
        query = query.strip()
        if not query:
            raise RAGValidationError("Query must not be empty")
        if len(query) > 1000:
            raise RAGValidationError("Query is too long")
        if not self.settings.rag_enabled:
            raise RAGError("Policy retrieval is disabled")
        result_count = top_k if top_k is not None else self.settings.rag_top_k
        if result_count < 1 or result_count > 10:
            raise RAGValidationError("top_k must be between 1 and 10")
        try:
            client = chromadb.PersistentClient(path=str(Path(self.settings.rag_persist_directory)))
            collection = client.get_collection(self.settings.rag_collection_name)
            model = _embedding_model(self.settings.rag_embedding_model)
            result = collection.query(
                query_embeddings=model.encode([query], normalize_embeddings=True).tolist(),
                n_results=result_count,
                include=["documents", "metadatas", "distances"],
            )
        except RAGError:
            raise
        except Exception as exc:
            raise RAGError("Policy retrieval is unavailable; ingest the configured policy first") from exc

        documents = (result.get("documents") or [[]])[0]
        metadata = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        rows = [
            {
                "text": text,
                "source": str(meta["document_name"]),
                "page": int(meta["page"]),
                "chunk_id": str(meta["chunk_id"]),
                "distance": float(distance) if distance is not None else None,
            }
            for text, meta, distance in zip(documents, metadata, distances)
        ]
        logger.info("Policy retrieval completed: result_count=%d", len(rows))
        return rows
