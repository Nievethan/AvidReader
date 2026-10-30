from __future__ import annotations

import io
import zipfile
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def _build_client(tmp_path, monkeypatch, **extra_env: str) -> TestClient:
    """Builds a TestClient wired to an isolated temp SQLite DB and
    uploads dir, so tests never touch real developer data. Extra env
    vars (e.g. MAX_UPLOAD_SIZE_BYTES) can be overridden per test."""
    db_path = tmp_path / "test.db"
    uploads_dir = tmp_path / "uploads"

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("UPLOADS_DIR", str(uploads_dir))
    monkeypatch.setenv("APP_ENV", "test")
    for key, value in extra_env.items():
        monkeypatch.setenv(key, value)

    # Settings and DB engine are cached at import time elsewhere, so
    # reset caches for each test.
    import app.api.deps as deps_module
    import app.core.config as config_module
    import app.db.database as database_module

    config_module.get_settings.cache_clear()
    deps_module.get_book_service.cache_clear()
    deps_module.get_progress_service.cache_clear()
    deps_module.get_ai_service.cache_clear()

    settings = config_module.get_settings()
    engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
    database_module.engine = engine
    database_module.SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    from app.main import create_app

    return TestClient(create_app())


@pytest.fixture()
def client(tmp_path, monkeypatch) -> Generator[TestClient, None, None]:
    with _build_client(tmp_path, monkeypatch) as test_client:
        yield test_client


@pytest.fixture()
def tiny_upload_limit_client(tmp_path, monkeypatch) -> Generator[TestClient, None, None]:
    """Same as `client`, but with a 10-byte upload size limit, to
    exercise the 413 path without needing a real multi-MB fixture file."""
    with _build_client(tmp_path, monkeypatch, MAX_UPLOAD_SIZE_BYTES="10") as test_client:
        yield test_client


def make_minimal_pdf_bytes() -> bytes:
    """A tiny but structurally valid single-page PDF, built inline so
    no copyrighted or external fixture file is committed to the repo."""
    return (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n"
        b"xref\n0 4\n0000000000 65535 f \n"
        b"trailer<</Root 1 0 R/Size 4>>\n%%EOF"
    )


def make_minimal_epub_bytes() -> bytes:
    """A minimal valid EPUB container: a zip whose first entry is an
    uncompressed 'mimetype' file, per the OCF spec."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip", zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", "<container/>")
    return buffer.getvalue()
