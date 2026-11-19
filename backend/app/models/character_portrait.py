from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CharacterPortrait(Base):
    """One AI-generated portrait per character per book.

    Kept separate from `CharacterGraphCache` on purpose: that cache is
    replaced wholesale on every "Update", while a portrait is generated once
    (the first Update that finds the character) and then reused forever --
    later chapters never regenerate or "upgrade" it. `aliases_json` holds the
    other char_ids (name variants such as "Dudley" -> "Dudley Dursley") that
    resolve to this same portrait."""

    __tablename__ = "character_portraits"

    book_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    char_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    aliases_json: Mapped[str] = mapped_column(Text, default="[]")
    appearance: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | ready | failed
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
