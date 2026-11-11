from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BookResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    author: str
    filename: str
    file_type: str
    file_size_bytes: int
    processing_status: str
    processing_message: str | None = None
    total_pages: int | None = None
    chunk_count: int | None = None
    created_at: datetime
    updated_at: datetime


class BookListResponse(BaseModel):
    items: list[BookResponse]
    total: int


class BookContentResponse(BaseModel):
    book_id: str
    status: str  # "ready" | "processing" | "not_available"
    content: str | None = None
    reason: str | None = None
    unit: str | None = None  # "page" (PDF) | "chapter" (EPUB)
    index: int | None = None  # 1-based page or chapter number returned
    total: int | None = None  # number of pages / chapters
    title: str | None = None  # chapter title when known


class IngestionStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    book_id: str
    status: str  # "uploaded" | "processing" | "ready" | "failed" | "unsupported"
    message: str | None = None
    total_pages: int | None = None
    chunk_count: int | None = None
    attempts: int = 0
    updated_at: datetime
