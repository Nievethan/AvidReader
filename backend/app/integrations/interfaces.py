"""Typed integration boundaries for teammates.

Umer (ingestion/retrieval) and Gitae (answer generation/character graph)
implement these Protocols with real logic later. The API layer only ever
depends on these interfaces, never on a concrete provider, so a real
implementation can be swapped in without touching route handlers.

Everything here is a data contract proposal -- adjust field names with
the owning teammate before they build against it, and update
docs/TEAM_INTEGRATION.md to match.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


# ---- Shared value objects -------------------------------------------------


@dataclass(frozen=True)
class ReadingBoundary:
    """What the reader has verified access to, for spoiler-safe retrieval."""

    book_id: str
    current_page: int | None = None
    current_chapter: int | None = None
    location: str | None = None


@dataclass(frozen=True)
class RetrievedPassage:
    book_id: str
    chunk_id: str
    text: str
    source_location: str  # e.g. "chapter 7" or "page 112"
    order_index: int  # position in reading order, used for spoiler filtering
    relevance_score: float | None = None


@dataclass(frozen=True)
class IngestionResult:
    book_id: str
    status: str  # "uploaded" | "processing" | "ready" | "failed" | "unsupported"
    total_pages: int | None = None
    error: str | None = None


@dataclass(frozen=True)
class GenerationRequest:
    book_id: str
    question: str
    mode: str  # "study" | "research" | "creative"
    interaction_type: str  # "question" | "explain" | "what_if" | "story_continues"
    reading_boundary: ReadingBoundary
    selected_passage: str | None = None
    explanation_level: str = "standard"
    conversation_history: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class GeneratedAnswer:
    answer: str
    answer_type: str  # "mock" | "grounded" | "hypothetical"
    is_hypothetical: bool
    citations: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class GraphResult:
    book_id: str
    status: str  # "not_available" | "ready"
    nodes: list[dict] = field(default_factory=list)
    edges: list[dict] = field(default_factory=list)
    source: str = "none"  # "none" | "fixture" | "extracted"


# ---- Provider protocols ----------------------------------------------------


class IngestionProvider(Protocol):
    """Owned by Umer. Parses an uploaded file into retrievable content."""

    async def ingest(self, book_id: str, file_path: str, file_type: str) -> IngestionResult: ...


class RetrievalProvider(Protocol):
    """Owned by Umer. Vector/keyword retrieval over a book's indexed content."""

    async def retrieve(
        self, book_id: str, question: str, reading_boundary: ReadingBoundary, limit: int = 5
    ) -> list[RetrievedPassage]: ...


class AnswerProvider(Protocol):
    """Owned by Gitae. Generates grounded or creative answers from retrieved sources."""

    async def answer(
        self, request: GenerationRequest, sources: list[RetrievedPassage]
    ) -> GeneratedAnswer: ...


class CharacterGraphProvider(Protocol):
    """Owned by Gitae. Produces character/relationship graphs within a spoiler boundary."""

    async def get_graph(self, book_id: str, boundary: ReadingBoundary) -> GraphResult: ...
