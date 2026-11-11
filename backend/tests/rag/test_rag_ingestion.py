import asyncio

import pytest

from app.integrations.rag_ingestion import NO_TEXT_MESSAGE, RagIngestionProvider
from app.rag.chunking import ChunkingConfig
from app.rag.embeddings import EmbeddingError, FakeEmbeddingProvider
from app.rag.extracted_store import ExtractedTextStore
from app.rag.models import ExtractedDocument, Section
from app.rag.vector_store import QdrantVectorStore, VectorStoreError
from tests.rag.conftest import build_blank_pdf


@pytest.fixture()
def parts(tmp_path):
    embedder = FakeEmbeddingProvider(64)
    store = QdrantVectorStore.in_memory(collection="t", dimension=64, embedding_model=embedder.model)
    text_store = ExtractedTextStore(tmp_path / "text")
    provider = RagIngestionProvider(embedder=embedder, store=store, text_store=text_store)
    return provider, store, text_store


def run(provider, path, kind="pdf", book_id="b"):
    return asyncio.run(provider.ingest(book_id, str(path), kind))


def test_pdf_ingestion_indexes_and_saves_text(parts, pdf_path):
    provider, store, text_store = parts
    result = run(provider, pdf_path)
    assert (result.status, result.total_pages, result.error) == ("ready", 8, None)
    assert result.chunk_count == store.count("b") > 0
    assert "dragon" in text_store.get_unit("b", 1).text


def test_epub_ingestion(parts, epub_path):
    provider, store, _ = parts
    result = run(provider, epub_path, "epub")
    assert (result.status, result.total_pages, result.chunk_count) == ("ready", None, 3)


def test_scanned_pdf_is_unsupported(parts, tmp_path):
    provider, _, text_store = parts
    result = run(provider, build_blank_pdf(tmp_path / "s.pdf"))
    assert result.status == "unsupported" and "scanned" in result.error
    assert not text_store.exists("b")


def test_unreadable_file_is_failed(parts, tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"garbage")
    result = run(parts[0], bad)
    assert result.status == "failed" and "Could not open PDF" in result.error


def test_document_without_chunks_is_unsupported(parts, monkeypatch, tmp_path):
    provider = parts[0]
    empty = ExtractedDocument("pdf", [Section(0, "", page=1)], 1)
    monkeypatch.setattr(provider, "_prepare", lambda *a: (empty, []))
    result = run(provider, tmp_path / "x.pdf")
    assert (result.status, result.error, result.total_pages) == ("unsupported", NO_TEXT_MESSAGE, 1)


@pytest.mark.parametrize("error", [EmbeddingError("quota exceeded"), VectorStoreError("bad dims")])
def test_embedding_or_store_errors_fail_cleanly(parts, pdf_path, monkeypatch, error):
    provider = parts[0]

    async def broken(texts):
        raise error

    monkeypatch.setattr(provider.embedder, "embed", broken)
    result = run(provider, pdf_path)
    assert (result.status, result.error, result.total_pages) == ("failed", str(error), 8)


def test_unexpected_error_fails_without_leaking_details(parts, pdf_path, monkeypatch):
    provider, store, _ = parts

    def explode(*args, **kwargs):
        raise OSError("disk full at /secret/path")

    monkeypatch.setattr(store, "upsert", explode)
    result = run(provider, pdf_path)
    assert result.status == "failed" and result.error == "Indexing failed (OSError)."


def test_reingest_replaces_old_chunks(parts, pdf_path):
    provider, store, _ = parts
    first = run(provider, pdf_path)
    provider.chunking = ChunkingConfig(target_tokens=25, overlap_ratio=0.0)  # many more, smaller chunks
    second = run(provider, pdf_path)
    provider.chunking = ChunkingConfig()
    third = run(provider, pdf_path)
    assert second.chunk_count > first.chunk_count
    assert store.count("b") == third.chunk_count == first.chunk_count  # no stale leftovers


def test_remove_deletes_everything_and_never_raises(parts, pdf_path, monkeypatch):
    provider, store, text_store = parts
    run(provider, pdf_path)
    provider.remove("b")
    assert store.count("b") == 0 and not text_store.exists("b")

    run(provider, pdf_path)

    def down(book_id):
        raise ConnectionError("down")

    def locked(book_id):
        raise PermissionError("locked")

    monkeypatch.setattr(store, "delete_book", down)
    monkeypatch.setattr(text_store, "delete", locked)
    provider.remove("b")  # both failures logged, nothing raised
