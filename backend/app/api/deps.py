from __future__ import annotations

from functools import lru_cache

from app.core.config import Settings, get_settings
from app.integrations.mock_ai import MockAnswerProvider
from app.integrations.mock_ingestion import MockIngestionProvider
from app.services.ai_service import AIService
from app.services.book_service import BookService
from app.services.progress_service import ProgressService


@lru_cache
def get_book_service() -> BookService:
    settings: Settings = get_settings()
    return BookService(settings=settings, ingestion_provider=MockIngestionProvider())


@lru_cache
def get_progress_service() -> ProgressService:
    return ProgressService()


@lru_cache
def get_ai_service() -> AIService:
    return AIService(answer_provider=MockAnswerProvider())
