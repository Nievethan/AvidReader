from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class WordWallEntryCreate(BaseModel):
    word: str = Field(min_length=1, max_length=200)
    meaning: str | None = Field(default=None, max_length=2000)
    quote: str | None = Field(default=None, max_length=2000)
    source_location: str | None = Field(default=None, max_length=255)


class WordWallEntryResponse(BaseModel):
    id: str
    book_id: str
    word: str
    meaning: str | None = None
    quote: str | None = None
    source_location: str | None = None
    created_at: datetime


class WordWallListResponse(BaseModel):
    items: list[WordWallEntryResponse]
    total: int
