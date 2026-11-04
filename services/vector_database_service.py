"""
services/vector_database_service.py — ChromaDB-backed semantic store for document
chunks.  Supports multi-document storage with duplicate detection and metadata.
"""

import logging
import os

import chromadb

import config
from granite_service import get_ibm_embedding_function

_COLLECTION_NAME = "study_materials"
logger = logging.getLogger(__name__)


class VectorDatabaseService:
    """Manages a persistent ChromaDB collection for document embeddings.

    Uses IBM watsonx.ai embeddings via IBMEmbeddingFunction so that no local
    sentence-transformers model is downloaded or run on CPU.

    If a collection already exists with a different (or default) embedding
    function it is deleted and recreated so the IBM embedding function is
    always active.
    """

    def __init__(self) -> None:
        os.makedirs(config.CHROMA_DB_PATH, exist_ok=True)
        self._client = chromadb.PersistentClient(path=config.CHROMA_DB_PATH)
        self._embedding_fn = get_ibm_embedding_function()
        self._collection = self._get_or_recreate_collection()

    def _get_or_recreate_collection(self):
        """Return the ChromaDB collection, recreating it if the embedding function
        is incompatible with what is already stored on disk."""
        try:
            return self._client.get_or_create_collection(
                _COLLECTION_NAME,
                embedding_function=self._embedding_fn,
            )
        except Exception as exc:
            # Existing collection was created with a different embedding function
            # (e.g. default sentence-transformers).  Drop and recreate it.
            logger.warning(
                "VectorDatabaseService: collection incompatible with IBM embedding "
                "function (%s) — recreating collection (existing data will be lost).",
                exc,
            )
            try:
                self._client.delete_collection(_COLLECTION_NAME)
            except Exception:
                pass
            return self._client.get_or_create_collection(
                _COLLECTION_NAME,
                embedding_function=self._embedding_fn,
            )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def get_chunk_count(self) -> int:
        """Return the total number of chunks stored in the collection."""
        return self._collection.count()

    # ── Duplicate detection ───────────────────────────────────────────────────

    def document_exists(self, doc_id: str) -> bool:
        """Return True if any chunk for *doc_id* is already stored."""
        if self.get_chunk_count() == 0:
            return False
        try:
            results = self._collection.get(
                where={"doc_id": doc_id},
                limit=1,
            )
            return bool(results["ids"])
        except Exception:
            return False

    # ── Write ─────────────────────────────────────────────────────────────────

    def add_document(self, doc_id: str, chunks: list[str], filename: str) -> bool:
        """Embed and store *chunks* for the given document.

        Returns False (skips) when *doc_id* is already present.
        Returns True when the chunks were successfully added.
        """
        if self.document_exists(doc_id):
            return False

        ids = [f"{doc_id}_chunk_{i}" for i in range(len(chunks))]
        metadatas = [
            {"doc_id": doc_id, "filename": filename, "chunk_index": i}
            for i in range(len(chunks))
        ]
        self._collection.add(ids=ids, documents=chunks, metadatas=metadatas)
        return True

    # ── Read ──────────────────────────────────────────────────────────────────

    def search(self, query: str, n_results: int = 5) -> list[dict]:
        """Return up to *n_results* chunks most semantically similar to *query*.

        Each result is a dict with keys: ``text``, ``filename``, ``doc_id``.
        Returns [] if the collection is empty.
        """
        count = self.get_chunk_count()
        if count == 0:
            return []

        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=min(n_results, count),
            )
        except Exception:
            return []

        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]

        return [
            {
                "text": doc,
                "filename": meta.get("filename", ""),
                "doc_id": meta.get("doc_id", ""),
            }
            for doc, meta in zip(documents, metadatas)
        ]

    def get_all_chunks_for_document(self, doc_id: str) -> list[str]:
        """Return all text chunks for *doc_id* sorted by chunk_index.

        Unlike search(), this returns the complete ordered content of the
        document rather than the top-N similarity matches.  Used by the
        detailed notes pipeline to process the entire PDF in sequence.
        Returns [] if no chunks are found.
        """
        if self.get_chunk_count() == 0:
            return []
        try:
            results = self._collection.get(where={"doc_id": doc_id})
        except Exception:
            return []

        ids = results.get("ids", [])
        documents = results.get("documents", [])
        metadatas = results.get("metadatas", [])

        if not documents:
            return []

        # Sort by chunk_index so we preserve the original document order
        triples = sorted(
            zip(ids, documents, metadatas),
            key=lambda t: t[2].get("chunk_index", 0) if t[2] else 0,
        )
        return [doc for _, doc, _ in triples]

    def list_documents(self) -> list[dict]:
        """Return unique documents stored: ``[{"doc_id": ..., "filename": ...}]``."""
        if self.get_chunk_count() == 0:
            return []

        try:
            results = self._collection.get()
        except Exception:
            return []

        seen: dict[str, str] = {}  # doc_id -> filename
        for meta in results.get("metadatas", []):
            if meta and meta.get("doc_id") and meta["doc_id"] not in seen:
                seen[meta["doc_id"]] = meta.get("filename", "")

        return [{"doc_id": did, "filename": fname} for did, fname in seen.items()]

    # ── Delete / reset ────────────────────────────────────────────────────────

    def delete_document(self, doc_id: str) -> None:
        """Remove all chunks belonging to *doc_id*."""
        if self.get_chunk_count() == 0:
            return
        try:
            self._collection.delete(where={"doc_id": doc_id})
        except Exception:
            pass

    def clear_all(self) -> None:
        """Wipe the entire collection and recreate it."""
        self._client.delete_collection(_COLLECTION_NAME)
        self._collection = self._client.get_or_create_collection(
            _COLLECTION_NAME,
            embedding_function=self._embedding_fn,
        )


# ── Module-level singleton ────────────────────────────────────────────────────

_vector_db_service: VectorDatabaseService | None = None


def get_vector_db_service() -> VectorDatabaseService:
    """Return the shared VectorDatabaseService instance (created on first call)."""
    global _vector_db_service
    if _vector_db_service is None:
        _vector_db_service = VectorDatabaseService()
    return _vector_db_service
