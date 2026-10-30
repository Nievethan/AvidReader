from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import FileTooLargeError, NotFoundError, UnsupportedFileError
from app.integrations.interfaces import IngestionProvider
from app.models.books import Book
from app.repositories import book_repository
from app.services.file_validation import detect_file_type, sanitize_filename


class BookService:
    def __init__(self, settings: Settings, ingestion_provider: IngestionProvider):
        self.settings = settings
        self.ingestion_provider = ingestion_provider

    async def upload_book(
        self,
        db: Session,
        *,
        raw: bytes,
        original_filename: str,
        title: str | None,
        author: str | None,
    ) -> Book:
        if len(raw) > self.settings.max_upload_size_bytes:
            raise FileTooLargeError(
                f"File exceeds the maximum allowed size of {self.settings.max_upload_size_bytes} bytes."
            )

        file_type = detect_file_type(raw)
        if file_type is None:
            raise UnsupportedFileError("Only valid PDF or EPUB files are supported.")

        safe_name = sanitize_filename(original_filename)
        book_id = str(uuid.uuid4())
        stored_name = f"{book_id}_{safe_name}"
        stored_path = self.settings.uploads_dir / stored_name

        self.settings.uploads_dir.mkdir(parents=True, exist_ok=True)
        stored_path.write_bytes(raw)

        book = Book(
            id=book_id,
            title=title or safe_name,
            author=author or "Unknown",
            filename=safe_name,
            stored_path=str(stored_path),
            file_type=file_type,
            file_size_bytes=len(raw),
            processing_status="uploaded",
            total_pages=None,
        )
        book = book_repository.create_book(db, book)

        # Hook for Umer's real ingestion pipeline. The mock keeps status
        # truthful ("uploaded") instead of claiming the file was parsed.
        result = await self.ingestion_provider.ingest(book.id, book.stored_path, book.file_type)
        book.processing_status = result.status
        book.total_pages = result.total_pages
        book.processing_message = result.error
        db.add(book)
        db.commit()
        db.refresh(book)
        return book

    def get_book_or_404(self, db: Session, book_id: str) -> Book:
        book = book_repository.get_book(db, book_id)
        if book is None:
            raise NotFoundError(f"Book {book_id} was not found.")
        return book

    def list_books(self, db: Session) -> list[Book]:
        return book_repository.list_books(db)

    def delete_book(self, db: Session, book_id: str) -> None:
        book = self.get_book_or_404(db, book_id)
        path = Path(book.stored_path)
        book_repository.delete_book(db, book)
        if path.exists():
            path.unlink()
