"""Environment-driven settings for the AvidReader backend.

All values have safe local-dev defaults so the backend runs on a clean
checkout with no `.env` file and no external services configured.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(BACKEND_ROOT / ".env")
DEFAULT_UPLOADS_DIR = BACKEND_ROOT / "data" / "uploads"
DEFAULT_DATABASE_URL = f"sqlite:///{(BACKEND_ROOT / 'data' / 'avidreader.db').as_posix()}"
DEFAULT_CORS_ORIGINS = ["http://localhost", "http://127.0.0.1", "http://10.0.2.2"]
DEFAULT_MAX_UPLOAD_SIZE_BYTES = 50 * 1024 * 1024


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    app_env: str = "local"
    database_url: str = DEFAULT_DATABASE_URL
    uploads_dir: Path = DEFAULT_UPLOADS_DIR
    max_upload_size_bytes: int = DEFAULT_MAX_UPLOAD_SIZE_BYTES
    cors_origins: list[str] = field(default_factory=lambda: list(DEFAULT_CORS_ORIGINS))

    # Optional integrations. Empty string means "not configured" -- the
    # backend must stay fully usable without any of these set.
    qdrant_url: str = ""
    neo4j_uri: str = ""
    neo4j_user: str = ""
    neo4j_password: str = ""

    @property
    def is_local(self) -> bool:
        return self.app_env == "local"


@lru_cache
def get_settings() -> Settings:
    uploads_dir_raw = os.environ.get("UPLOADS_DIR")
    cors_raw = os.environ.get("BACKEND_CORS_ORIGINS")

    return Settings(
        app_env=os.environ.get("APP_ENV", "local"),
        database_url=os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL),
        uploads_dir=Path(uploads_dir_raw) if uploads_dir_raw else DEFAULT_UPLOADS_DIR,
        max_upload_size_bytes=int(os.environ.get("MAX_UPLOAD_SIZE_BYTES", str(DEFAULT_MAX_UPLOAD_SIZE_BYTES))),
        cors_origins=_split_csv(cors_raw) if cors_raw else list(DEFAULT_CORS_ORIGINS),
        qdrant_url=os.environ.get("QDRANT_URL", ""),
        neo4j_uri=os.environ.get("NEO4J_URI", ""),
        neo4j_user=os.environ.get("NEO4J_USER", ""),
        neo4j_password=os.environ.get("NEO4J_PASSWORD", ""),
    )
