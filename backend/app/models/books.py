from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Book(Base):
    __tablename__ = "books"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(500))
    author: Mapped[str] = mapped_column(String(500), default="Unknown")
    filename: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(String(1024))
    file_type: Mapped[str] = mapped_column(String(10))  # "pdf" | "epub"
    file_size_bytes: Mapped[int] = mapped_column(Integer)

    # One of: uploaded, processing, ready, failed, unsupported
    processing_status: Mapped[str] = mapped_column(String(20), default="uploaded")
    processing_message: Mapped[str | None] = mapped_column(String(500), nullable=True)

    total_pages: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    progress: Mapped["BookProgress | None"] = relationship(
        back_populates="book", uselist=False, cascade="all, delete-orphan"
    )


class BookProgress(Base):
    __tablename__ = "book_progress"

    book_id: Mapped[str] = mapped_column(String(36), ForeignKey("books.id"), primary_key=True)
    current_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_chapter: Mapped[int | None] = mapped_column(Integer, nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    percent_complete: Mapped[float | None] = mapped_column(Float, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    book: Mapped[Book] = relationship(back_populates="progress")
