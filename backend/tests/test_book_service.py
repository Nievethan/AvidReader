"""BookService background ingestion, restart recovery and dependency wiring."""
from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app.api import deps
from app.db import database
from app.db.database import Base, add_missing_columns
from app.integrations.interfaces import IngestionResult
from app.models.books import Book
from app.services.book_service import INTERRUPTED_MESSAGE, MAX_INGESTION_ATTEMPTS, BookService
from tests.conftest import _build_client


class RecordingProvider:
    def __init__(self, result=None, error=None, on_ingest=None):
        self.result, self.error, self.on_ingest = result, error, on_ingest
        self.removed: list[str] = []
        self.calls = 0

    async def ingest(self, book_id, file_path, file_type):
        self.calls += 1
        if self.on_ingest:
            self.on_ingest(book_id)
        if self.error:
            raise self.error
        return self.result or IngestionResult(book_id=book_id, status="ready", total_pages=3, chunk_count=7)

    def remove(self, book_id):
        self.removed.append(book_id)


@pytest.fixture()
def session_factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'svc.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def make_service(tmp_path, session_factory, provider):
    from app.core.config import Settings

    settings = Settings(uploads_dir=tmp_path / "up", extracted_dir=tmp_path / "ex")
    return BookService(settings, provider, session_factory=session_factory)


def add_book(session_factory, book_id="b1", status="processing", attempts=0):
    with session_factory() as db:
        db.add(
            Book(
                id=book_id, title="t", filename="f.pdf", stored_path="/nowhere/f.pdf", file_type="pdf",
                file_size_bytes=1, processing_status=status, ingestion_attempts=attempts,
            )
        )
        db.commit()


def get_book(session_factory, book_id="b1"):
    with session_factory() as db:
        return db.get(Book, book_id)


def test_run_ingestion_records_result_and_counts_attempts(tmp_path, session_factory):
    add_book(session_factory)
    service = make_service(tmp_path, session_factory, RecordingProvider())
    asyncio.run(service.run_ingestion("b1"))
    book = get_book(session_factory)
    assert (book.processing_status, book.total_pages, book.chunk_count) == ("ready", 3, 7)
    assert book.ingestion_attempts == 1 and book.processing_message is None


def test_run_ingestion_for_deleted_book_does_nothing(tmp_path, session_factory):
    provider = RecordingProvider()
    asyncio.run(make_service(tmp_path, session_factory, provider).run_ingestion("missing"))
    assert provider.calls == 0


def test_provider_crash_marks_book_failed(tmp_path, session_factory):
    add_book(session_factory)
    service = make_service(tmp_path, session_factory, RecordingProvider(error=RuntimeError("bug")))
    asyncio.run(service.run_ingestion("b1"))
    book = get_book(session_factory)
    assert book.processing_status == "failed"
    assert book.processing_message == "Processing failed (RuntimeError)."


def test_book_deleted_during_ingestion_is_cleaned_up(tmp_path, session_factory):
    add_book(session_factory)

    def delete_mid_way(book_id):
        with session_factory() as db:
            db.delete(db.get(Book, book_id))
            db.commit()

    provider = RecordingProvider(on_ingest=delete_mid_way)
    asyncio.run(make_service(tmp_path, session_factory, provider).run_ingestion("b1"))
    assert provider.removed == ["b1"]
    assert get_book(session_factory) is None


def test_recover_interrupted_retries_once_then_fails(tmp_path, session_factory):
    add_book(session_factory, "fresh", attempts=0)  # saved, job never started
    add_book(session_factory, "once", attempts=1)  # first run interrupted
    add_book(session_factory, "twice", attempts=MAX_INGESTION_ATTEMPTS)  # retry interrupted too
    add_book(session_factory, "done", status="ready", attempts=1)
    service = make_service(tmp_path, session_factory, RecordingProvider())

    assert sorted(service.recover_interrupted()) == ["fresh", "once"]
    twice = get_book(session_factory, "twice")
    assert (twice.processing_status, twice.processing_message) == ("failed", INTERRUPTED_MESSAGE)
    assert get_book(session_factory, "done").processing_status == "ready"
    assert get_book(session_factory, "once").processing_status == "processing"


def test_startup_resumes_interrupted_ingestion(tmp_path, monkeypatch):
    # Seed a database with a book stuck in "processing", then start the app.
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    from tests.conftest import make_story_pdf_bytes

    pdf = uploads / "stuck.pdf"
    pdf.write_bytes(make_story_pdf_bytes(tmp_path))
    with sessionmaker(bind=engine)() as db:
        db.add(Book(id="stuck", title="t", filename="stuck.pdf", stored_path=str(pdf), file_type="pdf",
                    file_size_bytes=pdf.stat().st_size, processing_status="processing", ingestion_attempts=1))
        db.add(Book(id="dead", title="t", filename="x.pdf", stored_path=str(pdf), file_type="pdf",
                    file_size_bytes=1, processing_status="processing", ingestion_attempts=2))
        db.commit()
    engine.dispose()

    with _build_client(tmp_path, monkeypatch) as client:
        app = client.app
        for _ in range(200):  # the resumed job runs on the app's event loop
            if client.get("/api/v1/books/stuck/ingestion").json()["status"] != "processing":
                break
            client.portal.call(asyncio.sleep, 0.02)
        stuck = client.get("/api/v1/books/stuck/ingestion").json()
        assert stuck["status"] == "ready" and stuck["attempts"] == 2
        dead = client.get("/api/v1/books/dead/ingestion").json()
        assert (dead["status"], dead["message"]) == ("failed", INTERRUPTED_MESSAGE)
        assert app.state.recovery_tasks == set()


def test_shutdown_cancels_unfinished_recovery_tasks(tmp_path, monkeypatch):
    with _build_client(tmp_path, monkeypatch) as client:
        async def forever():
            await asyncio.sleep(3600)

        async def start():
            # Wrapped in a tuple: returning the task itself would make the
            # portal wait for it to finish, which it never does.
            return (asyncio.ensure_future(forever()),)

        (task,) = client.portal.call(start)
        client.app.state.recovery_tasks.add(task)
    assert task.cancelled()


def test_add_missing_columns_upgrades_old_database(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as connection:  # the books table as it was before Step 6
        connection.execute(text(
            "CREATE TABLE books (id VARCHAR(36) PRIMARY KEY, title VARCHAR(500), author VARCHAR(500), "
            "filename VARCHAR(255), stored_path VARCHAR(1024), file_type VARCHAR(10), file_size_bytes INTEGER, "
            "processing_status VARCHAR(20), processing_message VARCHAR(500), total_pages INTEGER, "
            "created_at DATETIME, updated_at DATETIME)"
        ))
        connection.execute(text("INSERT INTO books (id, title) VALUES ('old', 'Old book')"))

    assert sorted(add_missing_columns(engine)) == ["books.chunk_count", "books.ingestion_attempts"]
    columns = {c["name"] for c in inspect(engine).get_columns("books")}
    assert {"chunk_count", "ingestion_attempts"} <= columns
    with engine.connect() as connection:
        row = connection.execute(text("SELECT chunk_count, ingestion_attempts FROM books")).one()
    assert tuple(row) == (None, 0)
    assert add_missing_columns(engine) == []  # idempotent


def test_init_db_adds_columns_on_startup(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'boot.db'}")
    monkeypatch.setattr(database, "engine", engine)
    database.init_db()
    assert "chunk_count" in {c["name"] for c in inspect(engine).get_columns("books")}


# ---- dependency wiring ---------------------------------------------------------


def test_deps_build_cloudflare_client_only_with_credentials(monkeypatch):
    import app.core.config as config

    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok")
    config.get_settings.cache_clear()
    deps.reset_caches()
    try:
        client = deps.get_cloudflare_client()
        assert client is not None and deps.get_cloudflare_client() is client
        asyncio.run(deps.close_resources())
    finally:
        config.get_settings.cache_clear()
        deps.reset_caches()


def test_close_resources_tolerates_failures_and_unused_resources(monkeypatch):
    import app.core.config as config

    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "")
    monkeypatch.setenv("QDRANT_URL", "")
    monkeypatch.setenv("QDRANT_LOCAL_PATH", ":memory:")
    monkeypatch.setenv("EMBEDDING_BACKEND", "fake")
    config.get_settings.cache_clear()
    deps.reset_caches()
    try:
        asyncio.run(deps.close_resources())  # nothing created yet: no-op
        store = deps.get_vector_store()
        assert deps.get_cloudflare_client() is None

        def boom():
            raise RuntimeError("cannot close")

        monkeypatch.setattr(store, "close", boom)
        asyncio.run(deps.close_resources())  # logged, not raised
    finally:
        config.get_settings.cache_clear()
        deps.reset_caches()
