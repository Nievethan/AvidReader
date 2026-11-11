from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_book_service
from app.db.database import get_db
from app.schemas.books import BookContentResponse, BookListResponse, BookResponse, IngestionStatusResponse
from app.services.book_service import BookService

router = APIRouter(prefix="/books", tags=["books"])


@router.post("", response_model=BookResponse, status_code=status.HTTP_201_CREATED)
async def upload_book(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    author: str | None = Form(default=None),
    db: Session = Depends(get_db),
    service: BookService = Depends(get_book_service),
) -> BookResponse:
    """Stores the file and returns at once with `processing_status="processing"`.
    Indexing runs in the background; poll `GET /books/{id}/ingestion`."""
    raw = await file.read()
    book = await service.upload_book(
        db, raw=raw, original_filename=file.filename or "upload", title=title, author=author
    )
    response = BookResponse.model_validate(book)
    background_tasks.add_task(service.run_ingestion, book.id)
    return response


@router.get("", response_model=BookListResponse)
def list_books(
    db: Session = Depends(get_db), service: BookService = Depends(get_book_service)
) -> BookListResponse:
    books = service.list_books(db)
    items = [BookResponse.model_validate(book) for book in books]
    return BookListResponse(items=items, total=len(items))


@router.get("/{book_id}", response_model=BookResponse)
def get_book(
    book_id: str, db: Session = Depends(get_db), service: BookService = Depends(get_book_service)
) -> BookResponse:
    book = service.get_book_or_404(db, book_id)
    return BookResponse.model_validate(book)


@router.delete("/{book_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_book(
    book_id: str, db: Session = Depends(get_db), service: BookService = Depends(get_book_service)
) -> None:
    service.delete_book(db, book_id)


@router.get("/{book_id}/ingestion", response_model=IngestionStatusResponse)
def get_ingestion_status(
    book_id: str, db: Session = Depends(get_db), service: BookService = Depends(get_book_service)
) -> IngestionStatusResponse:
    book = service.get_book_or_404(db, book_id)
    return IngestionStatusResponse(
        book_id=book.id,
        status=book.processing_status,
        message=book.processing_message,
        total_pages=book.total_pages,
        chunk_count=book.chunk_count,
        attempts=book.ingestion_attempts or 0,
        updated_at=book.updated_at,
    )


@router.get("/{book_id}/content", response_model=BookContentResponse)
def get_book_content(
    book_id: str,
    page: int | None = Query(default=None, ge=1, description="Page number (PDF books)"),
    chapter: int | None = Query(default=None, ge=1, description="Chapter number (EPUB books)"),
    db: Session = Depends(get_db),
    service: BookService = Depends(get_book_service),
) -> BookContentResponse:
    """Extracted, cleaned text of one page (PDF) or chapter (EPUB)."""
    return service.get_content(db, book_id, page=page, chapter=chapter)
