from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.books import BookProgress
from app.repositories import book_repository
from app.schemas.reading import ProgressUpdateRequest
from app.services.reading_log_service import ReadingLogService


class ProgressService:
    def __init__(self, reading_log_service: ReadingLogService | None = None):
        self.reading_log_service = reading_log_service or ReadingLogService()

    def get_progress(self, db: Session, book_id: str) -> BookProgress | None:
        return book_repository.get_progress(db, book_id)

    def update_progress(self, db: Session, book_id: str, update: ProgressUpdateRequest) -> BookProgress:
        fields = update.model_dump(exclude_unset=True)
        progress = book_repository.upsert_progress(db, book_id, **fields)
        self.reading_log_service.log_activity(
            db, book_id, current_page=progress.current_page, current_chapter=progress.current_chapter
        )
        return progress
