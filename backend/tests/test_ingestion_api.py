"""Step 6 through the real HTTP routes: background ingestion, status, reader
text and delete, with the offline stack (fake embeddings, in-memory Qdrant)."""
from __future__ import annotations

from app.api import deps
from tests.conftest import (
    make_minimal_epub_bytes,
    make_minimal_pdf_bytes,
    make_story_epub_bytes,
    make_story_pdf_bytes,
    upload,
)


def test_pdf_is_indexed_in_the_background(client, tmp_path):
    created = upload(client, make_story_pdf_bytes(tmp_path), title="Harrow")
    assert created["processing_status"] == "processing"
    assert created["chunk_count"] is None

    status = client.get(f"/api/v1/books/{created['id']}/ingestion").json()
    assert status["status"] == "ready"
    assert status["total_pages"] == 8
    assert status["chunk_count"] >= 2
    assert status["attempts"] == 1
    assert status["message"] is None

    book = client.get(f"/api/v1/books/{created['id']}").json()
    assert (book["processing_status"], book["total_pages"]) == ("ready", 8)
    assert book["chunk_count"] == status["chunk_count"]
    assert deps.get_vector_store().count(created["id"]) == status["chunk_count"]


def test_epub_is_indexed_with_chapters(client, tmp_path):
    book_id = upload(client, make_story_epub_bytes(tmp_path), "b.epub", "application/epub+zip")["id"]
    status = client.get(f"/api/v1/books/{book_id}/ingestion").json()
    assert status["status"] == "ready"
    assert status["total_pages"] is None  # EPUBs have no pages
    assert status["chunk_count"] == 3


def test_scanned_pdf_is_unsupported(client):
    book_id = upload(client, make_minimal_pdf_bytes())["id"]
    status = client.get(f"/api/v1/books/{book_id}/ingestion").json()
    assert status["status"] == "unsupported"
    assert "scanned" in status["message"]
    assert status["chunk_count"] is None


def test_broken_epub_is_failed(client):
    book_id = upload(client, make_minimal_epub_bytes(), "b.epub", "application/epub+zip")["id"]
    status = client.get(f"/api/v1/books/{book_id}/ingestion").json()
    assert status["status"] == "failed"
    assert "EPUB" in status["message"]


def test_ingestion_status_for_missing_book_is_404(client):
    assert client.get("/api/v1/books/nope/ingestion").status_code == 404


def test_content_returns_cleaned_pages(client, tmp_path):
    book_id = upload(client, make_story_pdf_bytes(tmp_path))["id"]

    first = client.get(f"/api/v1/books/{book_id}/content").json()
    assert first["status"] == "ready"
    assert (first["unit"], first["index"], first["total"]) == ("page", 1, 8)
    assert first["title"] == "Part One: The Dragon"
    assert "dragon Ignis" in first["content"]
    assert "TEST BOOK" not in first["content"]  # running header removed

    third = client.get(f"/api/v1/books/{book_id}/content", params={"page": 3}).json()
    assert third["index"] == 3 and "international treaty" in third["content"]

    # a chapter parameter on a PDF falls back to being read as a page number
    as_chapter = client.get(f"/api/v1/books/{book_id}/content", params={"chapter": 5}).json()
    assert as_chapter["index"] == 5


def test_content_page_out_of_range_and_invalid(client, tmp_path):
    book_id = upload(client, make_story_pdf_bytes(tmp_path))["id"]
    missing = client.get(f"/api/v1/books/{book_id}/content", params={"page": 99})
    assert missing.status_code == 404
    assert "out of range (1-8)" in missing.json()["error"]["message"]
    assert client.get(f"/api/v1/books/{book_id}/content", params={"page": 0}).status_code == 422


def test_content_returns_epub_chapters(client, tmp_path):
    book_id = upload(client, make_story_epub_bytes(tmp_path), "b.epub", "application/epub+zip")["id"]
    second = client.get(f"/api/v1/books/{book_id}/content", params={"chapter": 2}).json()
    assert (second["unit"], second["index"], second["total"]) == ("chapter", 2, 3)
    assert second["title"] == "Chapter Two"
    assert "stranger" in second["content"]


def test_content_when_book_not_ready(client):
    book_id = upload(client, make_minimal_pdf_bytes())["id"]
    body = client.get(f"/api/v1/books/{book_id}/content").json()
    assert body["status"] == "not_available"
    assert body["content"] is None
    assert "scanned" in body["reason"]


def test_content_when_saved_text_is_missing(client, tmp_path):
    book_id = upload(client, make_story_pdf_bytes(tmp_path))["id"]
    deps.get_text_store().delete(book_id)  # e.g. processed by an older version
    body = client.get(f"/api/v1/books/{book_id}/content").json()
    assert body["status"] == "not_available"
    assert "Re-upload" in body["reason"]


def test_delete_removes_vectors_and_saved_text(client, tmp_path):
    book_id = upload(client, make_story_pdf_bytes(tmp_path))["id"]
    store, text_store = deps.get_vector_store(), deps.get_text_store()
    assert store.count(book_id) > 0 and text_store.exists(book_id)

    assert client.delete(f"/api/v1/books/{book_id}").status_code == 204
    assert store.count(book_id) == 0
    assert not text_store.exists(book_id)


def test_delete_still_works_when_qdrant_is_down(client, tmp_path, monkeypatch):
    book_id = upload(client, make_story_pdf_bytes(tmp_path))["id"]

    def down(_book_id):
        raise ConnectionError("qdrant unreachable")

    monkeypatch.setattr(deps.get_vector_store(), "delete_book", down)
    assert client.delete(f"/api/v1/books/{book_id}").status_code == 204
    assert client.get(f"/api/v1/books/{book_id}").status_code == 404
    assert not deps.get_text_store().exists(book_id)


def test_ready_reports_qdrant_error(client, monkeypatch):
    def broken():
        raise ConnectionError("refused")

    monkeypatch.setattr(deps.get_vector_store(), "ping", broken)
    body = client.get("/ready").json()
    assert body["status"] == "degraded"
    assert body["vector_store"]["status"] == "error"
    assert "ConnectionError: refused" in body["vector_store"]["message"]
