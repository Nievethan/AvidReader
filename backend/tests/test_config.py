import pytest

import app.core.config as config


@pytest.fixture(autouse=True)
def fresh_settings():
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


RAG_ENV = [
    "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_TEXT_MODEL", "CLOUDFLARE_EMBEDDING_MODEL",
    "EMBEDDING_DIMENSION", "EMBEDDING_BATCH_SIZE", "EMBEDDING_CONCURRENCY", "EMBEDDING_BACKEND",
    "QDRANT_COLLECTION", "CHUNK_TARGET_TOKENS", "CHUNK_OVERLAP_RATIO",
]


def test_rag_defaults(monkeypatch):
    for name in RAG_ENV:
        monkeypatch.delenv(name, raising=False)
    s = config.get_settings()
    assert (s.cloudflare_account_id, s.cloudflare_api_token, s.cloudflare_text_model) == ("", "", "")
    assert s.cloudflare_embedding_model == "@cf/baai/bge-base-en-v1.5"
    assert s.embedding_dimension == 768
    assert (s.embedding_batch_size, s.embedding_concurrency, s.embedding_backend) == (32, 4, "auto")
    assert s.qdrant_collection == "avidreader_chunks"
    assert (s.chunk_target_tokens, s.chunk_overlap_ratio) == (400, 0.12)


def test_rag_settings_read_from_environment(monkeypatch):
    values = {
        "CLOUDFLARE_ACCOUNT_ID": "acct", "CLOUDFLARE_API_TOKEN": "tok", "CLOUDFLARE_TEXT_MODEL": "@cf/chat",
        "CLOUDFLARE_EMBEDDING_MODEL": "@cf/embed", "EMBEDDING_DIMENSION": "384", "EMBEDDING_BATCH_SIZE": "10",
        "EMBEDDING_CONCURRENCY": "2", "EMBEDDING_BACKEND": "CloudFlare", "QDRANT_COLLECTION": "mine",
        "CHUNK_TARGET_TOKENS": "250", "CHUNK_OVERLAP_RATIO": "0.2",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    s = config.get_settings()
    assert (s.cloudflare_account_id, s.cloudflare_api_token, s.cloudflare_text_model) == ("acct", "tok", "@cf/chat")
    assert (s.cloudflare_embedding_model, s.embedding_dimension) == ("@cf/embed", 384)
    assert (s.embedding_batch_size, s.embedding_concurrency) == (10, 2)
    assert s.embedding_backend == "cloudflare"  # lower-cased
    assert s.qdrant_collection == "mine"
    assert (s.chunk_target_tokens, s.chunk_overlap_ratio) == (250, 0.2)


def test_existing_settings_still_parse(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("UPLOADS_DIR", str(tmp_path))
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", "http://a.test, http://b.test")
    monkeypatch.setenv("MAX_UPLOAD_SIZE_BYTES", "123")
    s = config.get_settings()
    assert not s.is_local
    assert s.uploads_dir == tmp_path
    assert s.cors_origins == ["http://a.test", "http://b.test"]
    assert s.max_upload_size_bytes == 123
