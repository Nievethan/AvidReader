"""Step 5: Qdrant vector store.

One collection for all books (not one per book). Every point's payload has
`book_id`, so search and delete always filter on it. Spoiler safety is
enforced here, in the query: `position <= max_position` (see
`Chunk.position`), not left to the prompt.

The collection records the embedding model and dimension in its metadata and
refuses to open against a different one -- switching models means
re-ingesting every book.

The client is synchronous (it also supports `QdrantClient(":memory:")` for
tests); async callers should run these methods in a thread
(`asyncio.to_thread`).
"""
from __future__ import annotations

import logging
import uuid
import warnings
from dataclasses import dataclass

from qdrant_client import QdrantClient, models

from app.rag.models import Chunk

logger = logging.getLogger(__name__)

_POINT_NAMESPACE = uuid.UUID("6f0c3c5e-2a53-4d2c-9d3e-5b6a1f6f7a10")
_UPSERT_BATCH = 64


class VectorStoreError(Exception):
    pass


class VectorStoreConfigError(VectorStoreError):
    """Existing collection was built with a different model/dimension."""


@dataclass(frozen=True)
class StoredChunk:
    chunk_id: str
    book_id: str
    order_index: int
    position: int
    text: str
    page_start: int | None
    page_end: int | None
    chapter: int | None
    chapter_title: str | None
    source_location: str
    score: float | None = None


def point_id(chunk_id: str) -> str:
    """Qdrant ids must be uint or UUID; derive a stable UUID from chunk_id so
    re-ingesting a book overwrites rather than duplicates."""
    return str(uuid.uuid5(_POINT_NAMESPACE, chunk_id))


def _book_filter(book_id: str, max_position: int | None = None) -> models.Filter:
    must: list[models.Condition] = [
        models.FieldCondition(key="book_id", match=models.MatchValue(value=book_id))
    ]
    if max_position is not None:
        must.append(models.FieldCondition(key="position", range=models.Range(lte=max_position)))
    return models.Filter(must=must)


class QdrantVectorStore:
    def __init__(
        self,
        client: QdrantClient,
        *,
        collection: str,
        dimension: int,
        embedding_model: str,
    ) -> None:
        self._client = client
        self.collection = collection
        self.dimension = dimension
        self.embedding_model = embedding_model

    @classmethod
    def from_url(cls, url: str, **kwargs) -> "QdrantVectorStore":
        return cls(QdrantClient(url=url, timeout=30), **kwargs)

    @classmethod
    def in_memory(cls, **kwargs) -> "QdrantVectorStore":
        return cls(QdrantClient(":memory:"), **kwargs)

    # -- setup ---------------------------------------------------------------

    def ensure_collection(self) -> None:
        """Create the collection and payload indexes if missing; otherwise
        verify it matches the configured model/dimension."""
        if not self._client.collection_exists(self.collection):
            self._client.create_collection(
                collection_name=self.collection,
                vectors_config=models.VectorParams(size=self.dimension, distance=models.Distance.COSINE),
                metadata={"embedding_model": self.embedding_model, "dimension": self.dimension},
            )
            logger.info("Created Qdrant collection %s (dim=%d)", self.collection, self.dimension)
        else:
            self._verify_existing()
        self._ensure_indexes()

    def _verify_existing(self) -> None:
        info = self._client.get_collection(self.collection)
        vectors = info.config.params.vectors
        size = getattr(vectors, "size", None)
        if size is not None and size != self.dimension:
            raise VectorStoreConfigError(
                f"Collection {self.collection!r} has vector size {size}, expected {self.dimension}. "
                "Re-ingest all books into a new collection after changing the embedding model."
            )
        stored_model = (info.config.metadata or {}).get("embedding_model")
        if stored_model and stored_model != self.embedding_model:
            raise VectorStoreConfigError(
                f"Collection {self.collection!r} was built with {stored_model!r}, "
                f"but the configured model is {self.embedding_model!r}."
            )

    def _ensure_indexes(self) -> None:
        with warnings.catch_warnings():
            # In-memory/local Qdrant ignores payload indexes and warns; the
            # server (Docker) honours them.
            warnings.filterwarnings("ignore", message="Payload indexes have no effect")
            self._create_indexes()

    def _create_indexes(self) -> None:
        for field, schema in (
            ("book_id", models.PayloadSchemaType.KEYWORD),
            ("position", models.PayloadSchemaType.INTEGER),
            ("order_index", models.PayloadSchemaType.INTEGER),
        ):
            self._client.create_payload_index(self.collection, field_name=field, field_schema=schema)

    # -- writes --------------------------------------------------------------

    def upsert(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        if len(chunks) != len(vectors):
            raise VectorStoreError(f"{len(chunks)} chunks but {len(vectors)} vectors.")
        for vector in vectors:
            if len(vector) != self.dimension:
                raise VectorStoreError(f"Vector has {len(vector)} dims; collection expects {self.dimension}.")
        points = [
            models.PointStruct(
                id=point_id(chunk.chunk_id),
                vector=vector,
                payload={
                    "book_id": chunk.book_id,
                    "chunk_id": chunk.chunk_id,
                    "order_index": chunk.order_index,
                    "position": chunk.position,
                    "page_start": chunk.page_start,
                    "page_end": chunk.page_end,
                    "chapter": chunk.chapter,
                    "chapter_title": chunk.chapter_title,
                    "source_location": chunk.source_location,
                    "text_hash": chunk.text_hash,
                    "text": chunk.text,
                },
            )
            for chunk, vector in zip(chunks, vectors)
        ]
        for start in range(0, len(points), _UPSERT_BATCH):
            self._client.upsert(self.collection, points=points[start : start + _UPSERT_BATCH], wait=True)

    def delete_book(self, book_id: str) -> None:
        """Remove every vector for a book. Safe to call for unknown books."""
        self._client.delete(
            self.collection,
            points_selector=models.FilterSelector(filter=_book_filter(book_id)),
            wait=True,
        )

    # -- reads ---------------------------------------------------------------

    def search(
        self,
        vector: list[float],
        book_id: str,
        *,
        max_position: int | None = None,
        limit: int = 5,
        min_score: float | None = None,
    ) -> list[StoredChunk]:
        """Nearest chunks of one book, best first. `max_position` is the
        spoiler boundary (page for PDF, chapter for EPUB); None = no limit."""
        if len(vector) != self.dimension:
            raise VectorStoreError(f"Query vector has {len(vector)} dims; collection expects {self.dimension}.")
        response = self._client.query_points(
            self.collection,
            query=vector,
            query_filter=_book_filter(book_id, max_position),
            limit=limit,
            score_threshold=min_score,
            with_payload=True,
        )
        return [_to_stored(p.payload, p.score) for p in response.points]

    def count(self, book_id: str) -> int:
        return self._client.count(self.collection, count_filter=_book_filter(book_id), exact=True).count


def _to_stored(payload: dict, score: float | None) -> StoredChunk:
    return StoredChunk(
        chunk_id=payload["chunk_id"],
        book_id=payload["book_id"],
        order_index=payload["order_index"],
        position=payload["position"],
        text=payload["text"],
        page_start=payload.get("page_start"),
        page_end=payload.get("page_end"),
        chapter=payload.get("chapter"),
        chapter_title=payload.get("chapter_title"),
        source_location=payload["source_location"],
        score=score,
    )


# Example point:
# {
#   "id": "generated-uuid",
#   "vector": [0.12, -0.35, 0.87, 0.21],
#   "payload": {
#     "book_id": "ml_book",
#     "chunk_id": "ml_book:15",
#     "order_index": 15,
#     "position": 26,
#     "page_start": 25,
#     "page_end": 26,
#     "chapter": 3,
#     "chapter_title": "Optimization Algorithms",
#     "source_location": "pages 25-26",
#     "text_hash": "sha256-hash...",
#     "text": "Gradient descent minimizes a loss function..."
#   }
# }