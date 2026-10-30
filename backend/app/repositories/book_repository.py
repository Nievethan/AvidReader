from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.books import Book, BookProgress


def create_book(db: Session, book: Book) -> Book:
    db.add(book)
    db.commit()
    db.refresh(book)
    return book


def get_book(db: Session, book_id: str) -> Book | None:
    return db.get(Book, book_id)


def list_books(db: Session) -> list[Book]:
    return list(db.scalars(select(Book).order_by(Book.created_at.desc())))


def delete_book(db: Session, book: Book) -> None:
    db.delete(book)
    db.commit()


def get_progress(db: Session, book_id: str) -> BookProgress | None:
    return db.get(BookProgress, book_id)


def upsert_progress(db: Session, book_id: str, **fields) -> BookProgress:
    progress = db.get(BookProgress, book_id)
    if progress is None:
        progress = BookProgress(book_id=book_id, **fields)
        db.add(progress)
    else:
        for key, value in fields.items():
            setattr(progress, key, value)
    db.commit()
    db.refresh(progress)
    return progress
