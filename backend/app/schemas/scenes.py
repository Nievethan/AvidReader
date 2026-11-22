from __future__ import annotations

from pydantic import BaseModel, Field


class SceneItem(BaseModel):
    id: str
    title: str
    caption: str = ""
    source_location: str  # e.g. "page 12" or "chapter 3"
    position: int
    status: str  # "pending" | "ready" | "failed"
    image_url: str | None = None


class ScenesResponse(BaseModel):
    book_id: str
    status: str  # "ready" | "not_available"
    message: str | None = None
    # Only scenes the reader has already reached (spoiler gate), in reading order.
    scenes: list[SceneItem] = Field(default_factory=list)


class SceneResult(BaseModel):
    """Answer to one Illustrate tap."""

    book_id: str
    status: str  # "ready" | "failed" (painting failed, retry) | "not_available" (see message)
    message: str | None = None
    scene: SceneItem | None = None
