"""Environment-driven settings for the AvidReader backend.

All values have safe local-dev defaults so the backend runs on a clean
checkout with no `.env` file and no external services configured.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(BACKEND_ROOT / ".env")
DEFAULT_UPLOADS_DIR = BACKEND_ROOT / "data" / "uploads"
DEFAULT_DATABASE_URL = f"sqlite:///{(BACKEND_ROOT / 'data' / 'avidreader.db').as_posix()}"
DEFAULT_CORS_ORIGINS = ["http://localhost", "http://127.0.0.1", "http://10.0.2.2"]
DEFAULT_MAX_UPLOAD_SIZE_BYTES = 50 * 1024 * 1024
DEFAULT_EMBEDDING_MODEL = "@cf/baai/bge-base-en-v1.5"
DEFAULT_EMBEDDING_DIMENSION = 768
# Chat model for grounded answers; chosen by scripts/benchmark_chat.py.
DEFAULT_TEXT_MODEL = "@cf/qwen/qwen3-30b-a3b-fp8"
DEFAULT_QDRANT_LOCAL_PATH = BACKEND_ROOT / "data" / "qdrant"
DEFAULT_EXTRACTED_DIR = BACKEND_ROOT / "data" / "extracted"


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _model_id(raw: str | None, default: str) -> str:
    """Workers AI model ids look like "@cf/vendor/name". A blank or
    malformed value (e.g. "cloudflare") falls back to the default instead of
    failing every request with "model not found"."""
    value = (raw or "").strip()
    if not value:
        return default
    if not value.startswith("@"):
        logger.warning("Ignoring invalid Cloudflare model id %r; using %s", value, default)
        return default
    return value


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

    # Cloudflare Workers AI. Env var names match Gitae's prototype script.
    cloudflare_account_id: str = ""
    cloudflare_api_token: str = ""
    cloudflare_text_model: str = DEFAULT_TEXT_MODEL  # chat model for grounded answers
    # Embedding model + dimension are pinned per Qdrant collection. Changing
    # either means re-ingesting every book. [Verify against Cloudflare docs]
    cloudflare_embedding_model: str = DEFAULT_EMBEDDING_MODEL
    embedding_dimension: int = DEFAULT_EMBEDDING_DIMENSION
    embedding_batch_size: int = 32
    embedding_concurrency: int = 4
    # "auto" = Cloudflare when credentials are set, otherwise the
    # deterministic fake (offline dev / tests). "cloudflare" and "fake"
    # force one or the other.
    embedding_backend: str = "auto"

    # RAG chunking / vector store.
    qdrant_collection: str = "avidreader_chunks"
    # Used when QDRANT_URL is blank: Qdrant's embedded local mode persists
    # vectors in this folder (":memory:" keeps them in RAM, for tests).
    qdrant_local_path: str = str(DEFAULT_QDRANT_LOCAL_PATH)
    # Cleaned per-page / per-chapter text written at ingestion, served by
    # GET /books/{id}/content.
    extracted_dir: Path = DEFAULT_EXTRACTED_DIR
    chunk_target_tokens: int = 400
    chunk_overlap_ratio: float = 0.12

    # Retrieval + grounded answers.
    retrieval_top_k: int = 8  # tuned with scripts/eval_rag.py (5 missed answers on adjacent chunks)
    retrieval_min_score: float = 0.5
    # "auto" = Cloudflare when credentials are set, otherwise a clearly
    # labelled offline extractive fake. "cloudflare" / "fake" force one.
    answer_backend: str = "auto"
    answer_max_tokens: int = 400
    answer_timeout_seconds: float = 20.0
    story_max_tokens: int = 450
    story_context_chunks: int = 3
    history_max_messages: int = 6

    @property
    def is_local(self) -> bool:
        return self.app_env == "local"


@lru_cache
def get_settings() -> Settings:
    uploads_dir_raw = os.environ.get("UPLOADS_DIR")
    cors_raw = os.environ.get("BACKEND_CORS_ORIGINS")
    extracted_raw = os.environ.get("EXTRACTED_DIR")

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
        cloudflare_account_id=os.environ.get("CLOUDFLARE_ACCOUNT_ID", ""),
        cloudflare_api_token=os.environ.get("CLOUDFLARE_API_TOKEN", ""),
        cloudflare_text_model=_model_id(os.environ.get("CLOUDFLARE_TEXT_MODEL"), DEFAULT_TEXT_MODEL),
        cloudflare_embedding_model=_model_id(
            os.environ.get("CLOUDFLARE_EMBEDDING_MODEL"), DEFAULT_EMBEDDING_MODEL
        ),
        embedding_dimension=int(os.environ.get("EMBEDDING_DIMENSION", str(DEFAULT_EMBEDDING_DIMENSION))),
        embedding_batch_size=int(os.environ.get("EMBEDDING_BATCH_SIZE", "32")),
        embedding_concurrency=int(os.environ.get("EMBEDDING_CONCURRENCY", "4")),
        embedding_backend=os.environ.get("EMBEDDING_BACKEND", "auto").lower(),
        qdrant_collection=os.environ.get("QDRANT_COLLECTION", "avidreader_chunks"),
        chunk_target_tokens=int(os.environ.get("CHUNK_TARGET_TOKENS", "400")),
        chunk_overlap_ratio=float(os.environ.get("CHUNK_OVERLAP_RATIO", "0.12")),
        qdrant_local_path=os.environ.get("QDRANT_LOCAL_PATH") or str(DEFAULT_QDRANT_LOCAL_PATH),
        extracted_dir=Path(extracted_raw) if extracted_raw else DEFAULT_EXTRACTED_DIR,
        retrieval_top_k=int(os.environ.get("RETRIEVAL_TOP_K", "8")),
        retrieval_min_score=float(os.environ.get("RETRIEVAL_MIN_SCORE", "0.5")),
        answer_backend=os.environ.get("ANSWER_BACKEND", "auto").lower(),
        answer_max_tokens=int(os.environ.get("ANSWER_MAX_TOKENS", "400")),
        answer_timeout_seconds=float(os.environ.get("ANSWER_TIMEOUT_SECONDS", "20")),
        story_max_tokens=int(os.environ.get("STORY_MAX_TOKENS", "450")),
        story_context_chunks=int(os.environ.get("STORY_CONTEXT_CHUNKS", "3")),
        history_max_messages=int(os.environ.get("HISTORY_MAX_MESSAGES", "6")),
    )
