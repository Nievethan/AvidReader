"""Real RetrievalProvider (roadmap Step 7).

* `retrieve`    semantic top-k for a question, spoiler-bounded
* `list_chunks` every passage up to the boundary in reading order (or only the
                last n), for features that need coverage rather than search:
                Gitae's character map / environment, and story_continues
* `format_passages` the numbered passage block that prompts consume

The spoiler boundary is applied inside the Qdrant query (`position <= limit`),
never left to the prompt.
"""
from __future__ import annotations

import asyncio

from app.integrations.interfaces import ReadingBoundary, RetrievedPassage
from app.rag.embeddings import EmbeddingProvider
from app.rag.vector_store import QdrantVectorStore, StoredChunk


def to_passage(chunk: StoredChunk) -> RetrievedPassage:
    return RetrievedPassage(
        book_id=chunk.book_id,
        chunk_id=chunk.chunk_id,
        text=chunk.text,
        source_location=chunk.source_location,
        order_index=chunk.order_index,
        relevance_score=chunk.score,
        page_start=chunk.page_start,
        page_end=chunk.page_end,
        chapter=chunk.chapter,
        chapter_title=chunk.chapter_title,
    )


def format_passages(passages: list[RetrievedPassage]) -> str:
    """Numbered block, e.g. "[S1] (page 12)\\n<text>". Marker numbers match
    the citation markers the answer validator expects."""
    return "\n\n".join(f"[S{i}] ({p.source_location})\n{p.text}" for i, p in enumerate(passages, start=1))


class RagRetrievalProvider:
    def __init__(
        self,
        *,
        embedder: EmbeddingProvider,
        store: QdrantVectorStore,
        top_k: int = 8,
        min_score: float | None = None,
    ) -> None:
        self.embedder = embedder
        self.store = store
        self.top_k = top_k
        self.min_score = min_score

    async def retrieve(
        self, book_id: str, question: str, reading_boundary: ReadingBoundary, limit: int | None = None
    ) -> list[RetrievedPassage]:
        if not question.strip():
            return []
        vector = (await self.embedder.embed([question]))[0]
        hits = await asyncio.to_thread(
            self.store.search,
            vector,
            book_id,
            max_position=reading_boundary.limit,
            limit=limit or self.top_k,
            min_score=self.min_score,
        )
        return [to_passage(hit) for hit in hits]

    async def list_chunks(
        self, book_id: str, reading_boundary: ReadingBoundary, last_n: int | None = None
    ) -> list[RetrievedPassage]:
        chunks = await asyncio.to_thread(
            self.store.list_chunks, book_id, max_position=reading_boundary.limit, last_n=last_n
        )
        return [to_passage(chunk) for chunk in chunks]
