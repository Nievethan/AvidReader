from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import FileTooLargeError, NotFoundError, UnsupportedFileError
from app.db import database
from app.integrations.interfaces import IngestionProvider, IngestionResult
from app.models.books import Book
from app.rag.extracted_store import ExtractedTextStore
from app.repositories import book_repository
from app.schemas.books import BookContentResponse
from app.services.file_validation import detect_file_type, sanitize_filename

logger = logging.getLogger(__name__)

# A book whose ingestion was interrupted (server restart) is retried
# automatically until it has been started this many times, then marked failed.
MAX_INGESTION_ATTEMPTS = 2
INTERRUPTED_MESSAGE = "Processing was interrupted twice; please re-upload the book."

_NOT_READY_REASONS = {
    "uploaded": "The book is stored but has not been processed yet.",
    "processing": "The book is still being processed. Try again in a moment.",
    "failed": "Processing failed for this book.",
    "unsupported": "This file has no extractable text (for example a scanned PDF).",
}


def _default_session_factory() -> Session:
    # Looked up at call time so tests can swap database.SessionLocal.
    return database.SessionLocal()


class BookService:
    def __init__(
        self,
        settings: Settings,
        ingestion_provider: IngestionProvider,
        text_store: ExtractedTextStore | None = None,
        session_factory: Callable[[], Session] = _default_session_factory,
    ):
        self.settings = settings
        self.ingestion_provider = ingestion_provider
        self.text_store = text_store or ExtractedTextStore(settings.extracted_dir)
        self.session_factory = session_factory

    # ---- upload / ingestion ---------------------------------------------------

    async def upload_book(
        self,
        db: Session,
        *,
        raw: bytes,
        original_filename: str,
        title: str | None,
        author: str | None,
    ) -> Book:
        """Validate and store the file, then return immediately with status
        "processing". The caller schedules `run_ingestion(book.id)` in the
        background (indexing a book takes seconds to minutes)."""
        if len(raw) > self.settings.max_upload_size_bytes:
            raise FileTooLargeError(
                f"File exceeds the maximum allowed size of {self.settings.max_upload_size_bytes} bytes."
            )

        file_type = detect_file_type(raw)
        if file_type is None:
            raise UnsupportedFileError("Only valid PDF or EPUB files are supported.")

        safe_name = sanitize_filename(original_filename)
        book_id = str(uuid.uuid4())
        stored_path = self.settings.uploads_dir / f"{book_id}_{safe_name}"

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
            processing_status="processing",
            processing_message=None,
            total_pages=None,
            chunk_count=None,
            ingestion_attempts=0,
        )
        return book_repository.create_book(db, book)

    async def run_ingestion(self, book_id: str) -> None:
        """Background job: index one book and record the outcome. Uses its own
        database sessions, never the (already closed) request session."""
        with self.session_factory() as db:
            book = book_repository.get_book(db, book_id)
            if book is None:  # deleted before the job started
                return
            book.ingestion_attempts = (book.ingestion_attempts or 0) + 1
            book.processing_status = "processing"
            book.processing_message = None
            db.commit()
            file_path, file_type = book.stored_path, book.file_type

        try:
            result = await self.ingestion_provider.ingest(book_id, file_path, file_type)
        except Exception as exc:  # a provider bug must not leave the book stuck in "processing"
            logger.exception("Ingestion provider crashed for book %s", book_id)
            result = IngestionResult(book_id=book_id, status="failed", error=f"Processing failed ({type(exc).__name__}).")

        with self.session_factory() as db:
            book = book_repository.get_book(db, book_id)
            if book is None:  # deleted while it was being indexed: clean up what was written
                self.ingestion_provider.remove(book_id)
                return
            book.processing_status = result.status
            book.processing_message = result.error
            book.total_pages = result.total_pages
            book.chunk_count = result.chunk_count
            db.commit()

    def recover_interrupted(self) -> list[str]:
        """Called at startup. Background jobs die with the server process, so
        any book still marked "processing" was interrupted. Retry each once
        (returns their ids for the caller to schedule); a book that has
        already been started MAX_INGESTION_ATTEMPTS times is marked failed so
        a file that crashes the server cannot cause a restart loop."""
        to_retry: list[str] = []
        with self.session_factory() as db:
            stuck = db.scalars(select(Book).where(Book.processing_status == "processing")).all()
            for book in stuck:
                if (book.ingestion_attempts or 0) >= MAX_INGESTION_ATTEMPTS:
                    book.processing_status = "failed"
                    book.processing_message = INTERRUPTED_MESSAGE
                else:
                    to_retry.append(book.id)
            db.commit()
        return to_retry

    # ---- reads ------------------------------------------------------------------

    def get_book_or_404(self, db: Session, book_id: str) -> Book:
        book = book_repository.get_book(db, book_id)
        if book is None:
            raise NotFoundError(f"Book {book_id} was not found.")
        return book

    def list_books(self, db: Session) -> list[Book]:
        return book_repository.list_books(db)

    def get_content(
        self, db: Session, book_id: str, *, page: int | None = None, chapter: int | None = None
    ) -> BookContentResponse:
        """Text of one page (PDF) or chapter (EPUB). Defaults to the first."""
        book = self.get_book_or_404(db, book_id)
        if book.processing_status != "ready":
            return BookContentResponse(
                book_id=book_id,
                status="processing" if book.processing_status in ("processing", "uploaded") else "not_available",
                reason=book.processing_message or _NOT_READY_REASONS.get(book.processing_status),
            )

        requested = page if book.file_type == "pdf" else chapter
        index = requested if requested is not None else (page or chapter or 1)
        try:
            unit = self.text_store.get_unit(book_id, index)
        except IndexError as exc:
            raise NotFoundError(str(exc)) from exc
        if unit is None:
            return BookContentResponse(
                book_id=book_id,
                status="not_available",
                reason="No saved text for this book (it was processed by an older version). Re-upload it.",
            )
        return BookContentResponse(
            book_id=book_id,
            status="ready",
            content=unit.text,
            unit=unit.unit,
            index=unit.index,
            total=unit.total,
            title=unit.title,
        )

    # ---- delete -----------------------------------------------------------------

    def delete_book(self, db: Session, book_id: str) -> None:
        book = self.get_book_or_404(db, book_id)
        path = Path(book.stored_path)
        book_repository.delete_book(db, book)
        if path.exists():
            path.unlink()
        # Vectors + saved text. Never raises, so deletion works while Qdrant is down.
        self.ingestion_provider.remove(book_id)
