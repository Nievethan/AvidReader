from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.engagement import WordWallEntry
from app.repositories import engagement_repository
from app.schemas.word_wall import WordWallEntryCreate


class WordWallService:
    def add_word(self, db: Session, book_id: str, entry: WordWallEntryCreate) -> WordWallEntry:
        word = WordWallEntry(book_id=book_id, **entry.model_dump())
        return engagement_repository.create_word(db, word)

    def list_words(self, db: Session, book_id: str) -> list[WordWallEntry]:
        return engagement_repository.list_words(db, book_id)

    def delete_word(self, db: Session, book_id: str, word_id: str) -> None:
        entry = engagement_repository.get_word(db, book_id, word_id)
        if entry is None:
            raise NotFoundError(f"Word Wall entry {word_id} was not found for this book.")
        engagement_repository.delete_word(db, entry)
