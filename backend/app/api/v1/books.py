from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_book_service
from app.db.database import get_db
from app.schemas.books import BookContentResponse, BookListResponse, BookResponse
from app.services.book_service import BookService

router = APIRouter(prefix="/books", tags=["books"])


@router.post("", response_model=BookResponse, status_code=status.HTTP_201_CREATED)
async def upload_book(
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    author: str | None = Form(default=None),
    db: Session = Depends(get_db),
    service: BookService = Depends(get_book_service),
) -> BookResponse:
    raw = await file.read()
    book = await service.upload_book(
        db, raw=raw, original_filename=file.filename or "upload", title=title, author=author
    )
    return BookResponse.model_validate(book)


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


@router.get("/{book_id}/content", response_model=BookContentResponse)
def get_book_content(
    book_id: str, db: Session = Depends(get_db), service: BookService = Depends(get_book_service)
) -> BookContentResponse:
    # Ensures the book exists (404s otherwise) before reporting content status.
    service.get_book_or_404(db, book_id)
    return BookContentResponse(
        book_id=book_id,
        status="not_available",
        content=None,
        reason="No ingestion/parsing pipeline is connected yet (Umer's work). "
        "Uploaded file is stored but not parsed into readable content.",
    )
