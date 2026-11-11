"""Real IngestionProvider (roadmap Step 6).

extract -> clean -> chunk -> embed -> Qdrant, plus the cleaned text saved for
the reader. CPU-bound work and blocking Qdrant calls run in worker threads so
the FastAPI event loop stays responsive.

Status mapping:
    ready        indexed successfully
    unsupported  scanned/image PDF, or a file with no readable text
    failed       anything else (corrupt file, embedding or Qdrant error)
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from app.integrations.interfaces import IngestionResult
from app.rag.chunking import ChunkingConfig, chunk_document
from app.rag.cleaning import clean_document
from app.rag.embeddings import EmbeddingError, EmbeddingProvider
from app.rag.extracted_store import ExtractedTextStore
from app.rag.extraction import ExtractionError, ScannedDocumentError, extract_document
from app.rag.models import Chunk, ExtractedDocument
from app.rag.vector_store import QdrantVectorStore, VectorStoreError

logger = logging.getLogger(__name__)

NO_TEXT_MESSAGE = "No readable text was found in this file."


class RagIngestionProvider:
    def __init__(
        self,
        *,
        embedder: EmbeddingProvider,
        store: QdrantVectorStore,
        text_store: ExtractedTextStore,
        chunking: ChunkingConfig | None = None,
    ) -> None:
        self.embedder = embedder
        self.store = store
        self.text_store = text_store
        self.chunking = chunking or ChunkingConfig()

    async def ingest(self, book_id: str, file_path: str, file_type: str) -> IngestionResult:
        try:
            doc, chunks = await asyncio.to_thread(self._prepare, book_id, Path(file_path), file_type)
        except ScannedDocumentError as exc:
            return IngestionResult(book_id=book_id, status="unsupported", error=str(exc))
        except ExtractionError as exc:
            return IngestionResult(book_id=book_id, status="failed", error=str(exc))

        if not chunks:
            return IngestionResult(book_id=book_id, status="unsupported", total_pages=doc.total_pages, error=NO_TEXT_MESSAGE)

        try:
            vectors = await self.embedder.embed([chunk.text for chunk in chunks])
            # Drop any previous index first: a re-ingest with a different
            # chunk size must not leave stale chunks behind.
            await asyncio.to_thread(self.store.delete_book, book_id)
            await asyncio.to_thread(self.store.upsert, chunks, vectors)
            await asyncio.to_thread(self.text_store.save, book_id, doc)
        except (EmbeddingError, VectorStoreError) as exc:
            return IngestionResult(book_id=book_id, status="failed", total_pages=doc.total_pages, error=str(exc))
        except Exception as exc:  # never let a background job die silently
            logger.exception("Ingestion of book %s failed", book_id)
            return IngestionResult(
                book_id=book_id,
                status="failed",
                total_pages=doc.total_pages,
                error=f"Indexing failed ({type(exc).__name__}).",
            )

        return IngestionResult(
            book_id=book_id, status="ready", total_pages=doc.total_pages, chunk_count=len(chunks)
        )

    def _prepare(self, book_id: str, path: Path, file_type: str) -> tuple[ExtractedDocument, list[Chunk]]:
        doc = clean_document(extract_document(path, file_type))
        return doc, chunk_document(book_id, doc, self.chunking)

    def remove(self, book_id: str) -> None:
        """Delete the book's vectors and saved text. Never raises: a book can
        always be deleted, even while Qdrant is down (leftover vectors are
        harmless because re-ingesting overwrites them by chunk id)."""
        try:
            self.store.delete_book(book_id)
        except Exception:
            logger.warning("Could not delete vectors for book %s; continuing", book_id, exc_info=True)
        try:
            self.text_store.delete(book_id)
        except OSError:
            logger.warning("Could not delete saved text for book %s", book_id, exc_info=True)
