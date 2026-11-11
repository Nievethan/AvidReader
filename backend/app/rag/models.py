"""Value objects shared by the RAG pipeline stages."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field


@dataclass(frozen=True)
class TocEntry:
    level: int
    title: str
    page: int  # 1-based


@dataclass(frozen=True)
class Section:
    """One extracted unit of reading order: a PDF page or an EPUB spine item."""

    order_index: int  # 0-based position in the document
    text: str
    page: int | None = None  # 1-based; PDFs only
    chapter: int | None = None  # 1-based; EPUB spine item, or PDF TOC chapter
    chapter_title: str | None = None


@dataclass(frozen=True)
class ExtractedDocument:
    kind: str  # "pdf" | "epub"
    sections: list[Section]
    total_pages: int | None  # None for EPUB (no stable pages)
    toc: list[TocEntry] = field(default_factory=list)


@dataclass(frozen=True)
class Chunk:
    chunk_id: str  # f"{book_id}:{order_index}"
    book_id: str
    order_index: int  # global 0-based position of the chunk in reading order
    text: str
    page_start: int | None  # None for EPUB
    page_end: int | None
    chapter: int | None
    chapter_title: str | None
    token_count: int

    @property
    def position(self) -> int:
        """Spoiler-boundary coordinate: last page the chunk touches (PDF) or
        its chapter number (EPUB). A reader at boundary B may see the chunk
        only if position <= B, so a chunk is never shown if any of its text
        lies beyond the reader."""
        if self.page_end is not None:
            return self.page_end
        return self.chapter if self.chapter is not None else 0

    @property
    def source_location(self) -> str:
        if self.page_start is not None and self.page_end is not None:
            if self.page_start == self.page_end:
                return f"page {self.page_start}"
            return f"pages {self.page_start}-{self.page_end}"
        if self.chapter is not None:
            return f"chapter {self.chapter}"
        return f"section {self.order_index + 1}"

    @property
    def text_hash(self) -> str:
        """Stable content hash, usable as an embedding-cache key."""
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()
