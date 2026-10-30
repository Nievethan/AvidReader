from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_book_service, get_progress_service
from app.db.database import get_db
from app.schemas.reading import ProgressResponse, ProgressUpdateRequest
from app.services.book_service import BookService
from app.services.progress_service import ProgressService

router = APIRouter(prefix="/books/{book_id}/progress", tags=["reading"])


@router.get("", response_model=ProgressResponse)
def get_progress(
    book_id: str,
    db: Session = Depends(get_db),
    book_service: BookService = Depends(get_book_service),
    progress_service: ProgressService = Depends(get_progress_service),
) -> ProgressResponse:
    book_service.get_book_or_404(db, book_id)
    progress = progress_service.get_progress(db, book_id)
    if progress is None:
        return ProgressResponse(book_id=book_id)
    return ProgressResponse(
        book_id=book_id,
        current_page=progress.current_page,
        current_chapter=progress.current_chapter,
        location=progress.location,
        percent_complete=progress.percent_complete,
        updated_at=progress.updated_at,
    )


@router.put("", response_model=ProgressResponse)
def update_progress(
    book_id: str,
    update: ProgressUpdateRequest,
    db: Session = Depends(get_db),
    book_service: BookService = Depends(get_book_service),
    progress_service: ProgressService = Depends(get_progress_service),
) -> ProgressResponse:
    book_service.get_book_or_404(db, book_id)
    progress = progress_service.update_progress(db, book_id, update)
    return ProgressResponse(
        book_id=book_id,
        current_page=progress.current_page,
        current_chapter=progress.current_chapter,
        location=progress.location,
        percent_complete=progress.percent_complete,
        updated_at=progress.updated_at,
    )
