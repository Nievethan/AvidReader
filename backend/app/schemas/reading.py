from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ProgressUpdateRequest(BaseModel):
    current_page: int | None = Field(default=None, ge=0)
    current_chapter: int | None = Field(default=None, ge=0)
    location: str | None = None
    percent_complete: float | None = Field(default=None, ge=0, le=100)


class ProgressResponse(BaseModel):
    book_id: str
    current_page: int | None = None
    current_chapter: int | None = None
    location: str | None = None
    percent_complete: float | None = None
    updated_at: datetime | None = None
