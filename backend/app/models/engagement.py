from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WordWallEntry(Base):
    __tablename__ = "word_wall_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    book_id: Mapped[str] = mapped_column(String(36), ForeignKey("books.id"))
    word: Mapped[str] = mapped_column(String(200))
    meaning: Mapped[str | None] = mapped_column(Text, nullable=True)
    quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ReadingLogEntry(Base):
    """One row per (book, calendar day) a reader made progress on. Upserted
    from ProgressService.update_progress; powers the reading streak and log."""

    __tablename__ = "reading_log_entries"
    __table_args__ = (UniqueConstraint("book_id", "activity_date", name="uq_reading_log_book_day"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    book_id: Mapped[str] = mapped_column(String(36), ForeignKey("books.id"))
    activity_date: Mapped[date] = mapped_column(Date)
    current_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_chapter: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
