from __future__ import annotations

from app.db import database
from app.models.engagement import WordWallEntry
from tests.conftest import make_minimal_pdf_bytes, upload


def test_add_list_and_delete_word(client):
    book = upload(client, make_minimal_pdf_bytes())
    book_id = book["id"]

    res = client.post(
        f"/api/v1/books/{book_id}/words",
        json={"word": "lugubrious", "meaning": "mournful", "quote": "a lugubrious sigh", "source_location": "page 4"},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["word"] == "lugubrious"
    assert body["meaning"] == "mournful"
    assert body["book_id"] == book_id
    word_id = body["id"]

    res = client.get(f"/api/v1/books/{book_id}/words")
    assert res.status_code == 200
    listed = res.json()
    assert listed["total"] == 1
    assert listed["items"][0]["word"] == "lugubrious"

    res = client.delete(f"/api/v1/books/{book_id}/words/{word_id}")
    assert res.status_code == 204

    res = client.get(f"/api/v1/books/{book_id}/words")
    assert res.json()["total"] == 0


def test_add_word_requires_only_the_word_itself(client):
    book = upload(client, make_minimal_pdf_bytes())
    res = client.post(f"/api/v1/books/{book['id']}/words", json={"word": "ephemeral"})
    assert res.status_code == 201, res.text
    assert res.json()["meaning"] is None


def test_words_are_scoped_to_their_book(client):
    book_a = upload(client, make_minimal_pdf_bytes())
    book_b = upload(client, make_minimal_pdf_bytes())
    added = client.post(f"/api/v1/books/{book_a['id']}/words", json={"word": "petrichor"}).json()

    res = client.get(f"/api/v1/books/{book_b['id']}/words")
    assert res.json()["total"] == 0

    res = client.delete(f"/api/v1/books/{book_b['id']}/words/{added['id']}")
    assert res.status_code == 404


def test_word_wall_404s_for_unknown_book(client):
    res = client.get("/api/v1/books/does-not-exist/words")
    assert res.status_code == 404


def test_deleting_a_book_removes_its_word_wall_entries(client):
    book = upload(client, make_minimal_pdf_bytes())
    client.post(f"/api/v1/books/{book['id']}/words", json={"word": "orphan-test"})

    res = client.delete(f"/api/v1/books/{book['id']}")
    assert res.status_code == 204

    with database.SessionLocal() as db:
        remaining = db.query(WordWallEntry).filter_by(book_id=book["id"]).count()
    assert remaining == 0
