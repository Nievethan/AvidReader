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
    created_at: datetime
    updated_at: datetime


class BookListResponse(BaseModel):
    items: list[BookResponse]
    total: int


class BookContentResponse(BaseModel):
    book_id: str
    status: str  # "not_available" | "ready"
    content: str | None = None
    reason: str | None = None
