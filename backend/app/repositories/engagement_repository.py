from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.engagement import ReadingLogEntry, WordWallEntry

# ---- Word Wall --------------------------------------------------------------


def create_word(db: Session, entry: WordWallEntry) -> WordWallEntry:
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def list_words(db: Session, book_id: str) -> list[WordWallEntry]:
    return list(
        db.scalars(
            select(WordWallEntry).where(WordWallEntry.book_id == book_id).order_by(WordWallEntry.created_at.desc())
        )
    )


def get_word(db: Session, book_id: str, word_id: str) -> WordWallEntry | None:
    entry = db.get(WordWallEntry, word_id)
    if entry is None or entry.book_id != book_id:
        return None
    return entry


def delete_word(db: Session, entry: WordWallEntry) -> None:
    db.delete(entry)
    db.commit()


# ---- Reading log --------------------------------------------------------------


def upsert_reading_log(
    db: Session,
    *,
    book_id: str,
    activity_date: date,
    current_page: int | None,
    current_chapter: int | None,
) -> ReadingLogEntry:
    entry = db.scalar(
        select(ReadingLogEntry).where(
            ReadingLogEntry.book_id == book_id, ReadingLogEntry.activity_date == activity_date
        )
    )
    if entry is None:
        entry = ReadingLogEntry(
            book_id=book_id,
            activity_date=activity_date,
            current_page=current_page,
            current_chapter=current_chapter,
        )
        db.add(entry)
    else:
        entry.current_page = current_page
        entry.current_chapter = current_chapter
    db.commit()
    db.refresh(entry)
    return entry


def list_reading_log(db: Session, *, limit_days: int = 60) -> list[ReadingLogEntry]:
    return list(
        db.scalars(select(ReadingLogEntry).order_by(ReadingLogEntry.activity_date.desc()).limit(limit_days))
    )


def list_all_activity_dates(db: Session) -> list[date]:
    return list(db.scalars(select(ReadingLogEntry.activity_date).distinct()))


def delete_for_book(db: Session, book_id: str) -> None:
    """Removes a deleted book's Word Wall entries and reading-log rows, so
    they don't linger as orphaned rows or skew future streak/achievement
    calculations."""
    for entry in db.scalars(select(WordWallEntry).where(WordWallEntry.book_id == book_id)):
        db.delete(entry)
    for entry in db.scalars(select(ReadingLogEntry).where(ReadingLogEntry.book_id == book_id)):
        db.delete(entry)
    db.commit()
