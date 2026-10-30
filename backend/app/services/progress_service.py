from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.books import BookProgress
from app.repositories import book_repository
from app.schemas.reading import ProgressUpdateRequest


class ProgressService:
    def get_progress(self, db: Session, book_id: str) -> BookProgress | None:
        return book_repository.get_progress(db, book_id)

    def update_progress(self, db: Session, book_id: str, update: ProgressUpdateRequest) -> BookProgress:
        fields = update.model_dump(exclude_unset=True)
        return book_repository.upsert_progress(db, book_id, **fields)
