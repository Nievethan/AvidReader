from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


def _make_engine():
    settings = get_settings()
    connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
    return create_engine(settings.database_url, connect_args=connect_args)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    """Create tables if they don't exist. No Alembic migrations yet --
    documented as a known limitation in docs/BACKEND_CONTEXT.md."""
    from app import models  # noqa: F401  (ensure models are registered on Base)

    settings = get_settings()
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    add_missing_columns(engine)


# Columns added after the first release. `create_all` never alters an
# existing table, so older local databases get them added here.
_ADDED_COLUMNS: dict[str, dict[str, str]] = {
    "books": {
        "chunk_count": "INTEGER",
        "ingestion_attempts": "INTEGER NOT NULL DEFAULT 0",
    },
}


def add_missing_columns(bind) -> list[str]:
    """Add any column from `_ADDED_COLUMNS` that the live table lacks.
    Returns the "table.column" names it added."""
    added: list[str] = []
    inspector = inspect(bind)
    with bind.begin() as connection:
        for table, columns in _ADDED_COLUMNS.items():
            existing = {column["name"] for column in inspector.get_columns(table)}
            for name, ddl in columns.items():
                if name not in existing:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
                    added.append(f"{table}.{name}")
    return added


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
