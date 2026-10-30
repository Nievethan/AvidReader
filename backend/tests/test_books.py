from __future__ import annotations

from tests.conftest import make_minimal_epub_bytes, make_minimal_pdf_bytes


def test_upload_pdf_persists_truthful_metadata(client):
    response = client.post(
        "/api/v1/books",
        files={"file": ("sample.pdf", make_minimal_pdf_bytes(), "application/pdf")},
        data={"title": "Sample Book", "author": "Jane Doe"},
    )
    assert response.status_code == 201
    body = response.json()

    assert body["title"] == "Sample Book"
    assert body["author"] == "Jane Doe"
    assert body["file_type"] == "pdf"
    assert body["processing_status"] == "uploaded"
    assert body["total_pages"] is None  # must not fabricate a page count


def test_upload_epub_detects_type_from_contents(client):
    response = client.post(
        "/api/v1/books",
        files={"file": ("sample.epub", make_minimal_epub_bytes(), "application/epub+zip")},
    )
    assert response.status_code == 201
    assert response.json()["file_type"] == "epub"


def test_upload_rejects_file_that_is_not_really_pdf_or_epub(client):
    response = client.post(
        "/api/v1/books",
        files={"file": ("sample.txt", b"just some text", "text/plain")},
    )
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"


def test_upload_rejects_fake_pdf_extension_with_wrong_contents(client):
    """Extension lies, but the magic bytes don't -- must be rejected."""
    response = client.post(
        "/api/v1/books",
        files={"file": ("fake.pdf", b"not actually a pdf", "application/pdf")},
    )
    assert response.status_code == 415


def test_list_get_and_delete_book_lifecycle(client):
    upload = client.post(
        "/api/v1/books",
        files={"file": ("sample.pdf", make_minimal_pdf_bytes(), "application/pdf")},
    )
    book_id = upload.json()["id"]

    listed = client.get("/api/v1/books")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["id"] == book_id

    fetched = client.get(f"/api/v1/books/{book_id}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == book_id

    deleted = client.delete(f"/api/v1/books/{book_id}")
    assert deleted.status_code == 204

    missing = client.get(f"/api/v1/books/{book_id}")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "NOT_FOUND"


def test_upload_rejects_file_exceeding_configured_size_limit(tiny_upload_limit_client):
    response = tiny_upload_limit_client.post(
        "/api/v1/books",
        files={"file": ("sample.pdf", make_minimal_pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"


def test_delete_book_removes_stored_file_from_disk(client, tmp_path):
    upload = client.post(
        "/api/v1/books",
        files={"file": ("sample.pdf", make_minimal_pdf_bytes(), "application/pdf")},
    )
    book_id = upload.json()["id"]

    uploads_dir = tmp_path / "uploads"
    stored_files = list(uploads_dir.glob(f"{book_id}_*"))
    assert len(stored_files) == 1
    assert stored_files[0].exists()

    delete_response = client.delete(f"/api/v1/books/{book_id}")
    assert delete_response.status_code == 204
    assert not stored_files[0].exists()


def test_get_book_content_is_honestly_not_available(client):
    upload = client.post(
        "/api/v1/books",
        files={"file": ("sample.pdf", make_minimal_pdf_bytes(), "application/pdf")},
    )
    book_id = upload.json()["id"]

    content = client.get(f"/api/v1/books/{book_id}/content")
    assert content.status_code == 200
    body = content.json()
    assert body["status"] == "not_available"
    assert body["content"] is None
