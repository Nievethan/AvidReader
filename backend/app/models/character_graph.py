from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CharacterGraphCache(Base):
    """One cached character-map result per book, replaced wholesale each
    time the reader clicks "Update" -- not auto-regenerated on every view,
    so GET is free and the Cloudflare call only happens on request."""

    __tablename__ = "character_graph_cache"

    book_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    nodes_json: Mapped[str] = mapped_column(Text, default="[]")
    edges_json: Mapped[str] = mapped_column(Text, default="[]")
    # What boundary ("page 42" / "chapter 3") the cached graph was built from.
    boundary_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
