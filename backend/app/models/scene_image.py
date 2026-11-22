from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SceneImage(Base):
    """One illustrated page (PDF) or chapter (EPUB), made when the reader taps
    "Illustrate" on it.

    `position` is in the book's own unit (1-based page for PDF, chapter for
    EPUB). The spoiler gate compares it against the reader's progress: a
    scene is only listed or served once the reader has reached it. One scene
    per position; it is generated once and reused, never regenerated."""

    __tablename__ = "scene_images"

    book_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scene_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    order_index: Mapped[int] = mapped_column(Integer)  # chunk position in reading order
    position: Mapped[int] = mapped_column(Integer)  # page or chapter, for the spoiler gate
    source_location: Mapped[str] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(String(200))
    caption: Mapped[str] = mapped_column(Text, default="")
    evidence: Mapped[str] = mapped_column(Text, default="")
    prompt: Mapped[str] = mapped_column(Text, default="")
    image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | ready | failed
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
