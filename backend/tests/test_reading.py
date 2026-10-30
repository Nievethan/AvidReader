from __future__ import annotations

from tests.conftest import make_minimal_pdf_bytes


def _upload_book(client) -> str:
    response = client.post(
        "/api/v1/books",
        files={"file": ("sample.pdf", make_minimal_pdf_bytes(), "application/pdf")},
    )
    return response.json()["id"]


def test_progress_defaults_to_empty_before_any_update(client):
    book_id = _upload_book(client)
    response = client.get(f"/api/v1/books/{book_id}/progress")
    assert response.status_code == 200
    body = response.json()
    assert body["book_id"] == book_id
    assert body["current_page"] is None
    assert body["updated_at"] is None


def test_progress_update_persists_and_is_retrievable(client):
    book_id = _upload_book(client)

    update = client.put(
        f"/api/v1/books/{book_id}/progress",
        json={"current_page": 112, "current_chapter": 7, "percent_complete": 35.0},
    )
    assert update.status_code == 200
    body = update.json()
    assert body["current_page"] == 112
    assert body["current_chapter"] == 7
    assert body["percent_complete"] == 35.0
    assert body["updated_at"] is not None

    fetched = client.get(f"/api/v1/books/{book_id}/progress")
    assert fetched.json()["current_page"] == 112


def test_progress_rejects_negative_page(client):
    book_id = _upload_book(client)
    response = client.put(f"/api/v1/books/{book_id}/progress", json={"current_page": -1})
    assert response.status_code == 422


def test_progress_for_missing_book_returns_404(client):
    response = client.get("/api/v1/books/does-not-exist/progress")
    assert response.status_code == 404
