"""Dependency wiring. Every provider is built once per process (lru_cache)
and shared; `reset_caches()` rebuilds everything (tests, settings changes)."""
from __future__ import annotations

import logging
from functools import lru_cache

from app.core.config import Settings, get_settings
from app.integrations.character_graph import LLMCharacterGraphProvider, NotAvailableCharacterGraphProvider
from app.integrations.cloudflare import CloudflareClient
from app.integrations.grounded_answer import GroundedAnswerProvider
from app.integrations.interfaces import CharacterGraphProvider
from app.integrations.portraits import (
    CharacterDescriber,
    CloudflarePortraitGenerator,
    NotAvailablePortraitGenerator,
    PortraitGenerator,
)
from app.integrations.rag_ingestion import RagIngestionProvider
from app.integrations.rag_retrieval import RagRetrievalProvider
from app.integrations.scenes import LLMScenePicker, NotAvailableScenePicker
from app.rag.chunking import ChunkingConfig
from app.rag.embeddings import EmbeddingProvider, build_embedding_provider
from app.rag.extracted_store import ExtractedTextStore
from app.rag.llm import CloudflareChatModel, build_chat_model
from app.rag.vector_store import QdrantVectorStore, build_vector_store
from app.services.achievements_service import AchievementsService
from app.services.ai_service import AIService
from app.services.book_service import BookService
from app.services.portrait_service import PortraitService
from app.services.progress_service import ProgressService
from app.services.reading_log_service import ReadingLogService
from app.services.scene_service import SceneService
from app.services.word_wall_service import WordWallService

logger = logging.getLogger(__name__)


@lru_cache
def get_cloudflare_client() -> CloudflareClient | None:
    """One shared client (connection pool) for embeddings and chat, or None
    when no credentials are configured."""
    settings = get_settings()
    if not (settings.cloudflare_account_id and settings.cloudflare_api_token):
        return None
    return CloudflareClient(settings.cloudflare_account_id, settings.cloudflare_api_token)


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    return build_embedding_provider(get_settings(), client=get_cloudflare_client())


@lru_cache
def get_vector_store() -> QdrantVectorStore:
    embedder = get_embedding_provider()
    return build_vector_store(get_settings(), dimension=embedder.dimension, embedding_model=embedder.model)


@lru_cache
def get_text_store() -> ExtractedTextStore:
    return ExtractedTextStore(get_settings().extracted_dir)


@lru_cache
def get_ingestion_provider() -> RagIngestionProvider:
    settings = get_settings()
    return RagIngestionProvider(
        embedder=get_embedding_provider(),
        store=get_vector_store(),
        text_store=get_text_store(),
        chunking=ChunkingConfig(settings.chunk_target_tokens, settings.chunk_overlap_ratio),
    )


@lru_cache
def get_retrieval_provider() -> RagRetrievalProvider:
    settings = get_settings()
    return RagRetrievalProvider(
        embedder=get_embedding_provider(),
        store=get_vector_store(),
        top_k=settings.retrieval_top_k,
        min_score=settings.retrieval_min_score,
    )


@lru_cache
def get_answer_provider() -> GroundedAnswerProvider:
    settings = get_settings()
    return GroundedAnswerProvider(
        build_chat_model(settings, client=get_cloudflare_client()),
        max_tokens=settings.answer_max_tokens,
        story_max_tokens=settings.story_max_tokens,
    )


@lru_cache
def get_book_service() -> BookService:
    settings: Settings = get_settings()
    return BookService(settings=settings, ingestion_provider=get_ingestion_provider(), text_store=get_text_store())


@lru_cache
def get_reading_log_service() -> ReadingLogService:
    return ReadingLogService()


@lru_cache
def get_progress_service() -> ProgressService:
    return ProgressService(reading_log_service=get_reading_log_service())


@lru_cache
def get_word_wall_service() -> WordWallService:
    return WordWallService()


@lru_cache
def get_achievements_service() -> AchievementsService:
    return AchievementsService()


@lru_cache
def get_character_graph_provider() -> CharacterGraphProvider:
    settings = get_settings()
    client = get_cloudflare_client()
    if client is None:
        return NotAvailableCharacterGraphProvider()
    chat_model = CloudflareChatModel(
        client, settings.cloudflare_text_model, timeout=settings.character_map_timeout_seconds
    )
    return LLMCharacterGraphProvider(
        retrieval_provider=get_retrieval_provider(),
        chat_model=chat_model,
        max_tokens=settings.character_map_max_tokens,
        batch_chars=settings.character_map_batch_chars,
        max_batches=settings.character_map_max_batches,
    )


@lru_cache
def get_portrait_generator() -> PortraitGenerator:
    """Cloudflare text-to-image when credentials are set; otherwise no
    portraits are generated and the UI keeps its role icons."""
    settings = get_settings()
    client = get_cloudflare_client()
    if client is None:
        return NotAvailablePortraitGenerator()
    return CloudflarePortraitGenerator(
        client,
        settings.cloudflare_image_model,
        steps=settings.portrait_steps,
        timeout=settings.portrait_timeout_seconds,
    )


@lru_cache
def get_portrait_service() -> PortraitService:
    settings = get_settings()
    client = get_cloudflare_client()
    describer = None
    if client is not None and settings.portrait_describe_pass:
        describer = CharacterDescriber(
            chat_model=CloudflareChatModel(
                client, settings.cloudflare_text_model, timeout=settings.character_map_timeout_seconds
            ),
            retrieval_provider=get_retrieval_provider(),
            max_chars=settings.portrait_describe_max_chars,
        )
    return PortraitService(
        generator=get_portrait_generator(),
        portraits_dir=settings.portraits_dir,
        concurrency=settings.portrait_concurrency,
        describer=describer,
    )


@lru_cache
def get_scene_service() -> SceneService:
    """Scene pictures reuse the character map's chat model settings and the
    portrait image generator (same Cloudflare client, same image model)."""
    settings = get_settings()
    client = get_cloudflare_client()
    if client is None:
        picker = NotAvailableScenePicker()
        retrieval = None
    else:
        chat_model = CloudflareChatModel(
            client, settings.cloudflare_text_model, timeout=settings.character_map_timeout_seconds
        )
        picker = LLMScenePicker(chat_model, max_tokens=settings.scene_max_tokens)
        retrieval = get_retrieval_provider()
    return SceneService(
        picker=picker,
        generator=get_portrait_generator(),
        retrieval_provider=retrieval,
        scenes_dir=settings.scenes_dir,
        max_page_chars=settings.character_map_batch_chars,
    )


@lru_cache
def get_ai_service() -> AIService:
    settings = get_settings()
    return AIService(
        answer_provider=get_answer_provider(),
        retrieval_provider=get_retrieval_provider(),
        history_max_messages=settings.history_max_messages,
        story_context_chunks=settings.story_context_chunks,
    )


_CACHED = (
    get_cloudflare_client,
    get_embedding_provider,
    get_vector_store,
    get_text_store,
    get_ingestion_provider,
    get_retrieval_provider,
    get_answer_provider,
    get_book_service,
    get_reading_log_service,
    get_progress_service,
    get_word_wall_service,
    get_achievements_service,
    get_character_graph_provider,
    get_portrait_generator,
    get_portrait_service,
    get_scene_service,
    get_ai_service,
)


async def close_resources() -> None:
    """Release the HTTP pool and the embedded-Qdrant folder lock (only for
    resources that were actually created)."""
    if get_vector_store.cache_info().currsize:
        try:
            get_vector_store().close()
        except Exception:  # shutting down: never block on cleanup
            logger.warning("Could not close the vector store", exc_info=True)
    if get_cloudflare_client.cache_info().currsize:
        client = get_cloudflare_client()
        if client is not None:
            await client.aclose()


def reset_caches() -> None:
    for factory in _CACHED:
        factory.cache_clear()
