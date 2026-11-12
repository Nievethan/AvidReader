from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_book_service, get_word_wall_service
from app.db.database import get_db
from app.schemas.word_wall import WordWallEntryCreate, WordWallEntryResponse, WordWallListResponse
from app.services.book_service import BookService
from app.services.word_wall_service import WordWallService

router = APIRouter(prefix="/books/{book_id}/words", tags=["word-wall"])


@router.post("", response_model=WordWallEntryResponse, status_code=status.HTTP_201_CREATED)
def add_word(
    book_id: str,
    entry: WordWallEntryCreate,
    db: Session = Depends(get_db),
    book_service: BookService = Depends(get_book_service),
    word_wall_service: WordWallService = Depends(get_word_wall_service),
) -> WordWallEntryResponse:
    book_service.get_book_or_404(db, book_id)
    word = word_wall_service.add_word(db, book_id, entry)
    return WordWallEntryResponse.model_validate(word, from_attributes=True)


@router.get("", response_model=WordWallListResponse)
def list_words(
    book_id: str,
    db: Session = Depends(get_db),
    book_service: BookService = Depends(get_book_service),
    word_wall_service: WordWallService = Depends(get_word_wall_service),
) -> WordWallListResponse:
    book_service.get_book_or_404(db, book_id)
    words = word_wall_service.list_words(db, book_id)
    items = [WordWallEntryResponse.model_validate(w, from_attributes=True) for w in words]
    return WordWallListResponse(items=items, total=len(items))


@router.delete("/{word_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_word(
    book_id: str,
    word_id: str,
    db: Session = Depends(get_db),
    book_service: BookService = Depends(get_book_service),
    word_wall_service: WordWallService = Depends(get_word_wall_service),
) -> None:
    book_service.get_book_or_404(db, book_id)
    word_wall_service.delete_word(db, book_id, word_id)
