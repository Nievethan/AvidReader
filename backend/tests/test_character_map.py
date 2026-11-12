from __future__ import annotations

import json

import pytest

from app.api.deps import get_character_graph_provider
from app.integrations.character_graph import LLMCharacterGraphProvider, NotAvailableCharacterGraphProvider, _normalize
from app.integrations.interfaces import GraphResult, ReadingBoundary, RetrievedPassage
from tests.conftest import make_minimal_pdf_bytes, upload


def _passage(chunk_id: str, text: str, order_index: int = 0) -> RetrievedPassage:
    return RetrievedPassage(
        book_id="book-1", chunk_id=chunk_id, text=text, source_location=f"page {order_index + 1}",
        order_index=order_index,
    )


def test_relationships_are_honestly_not_available_before_generation(client):
    book = upload(client, make_minimal_pdf_bytes())
    res = client.get(f"/api/v1/books/{book['id']}/relationships")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "not_available"
    assert body["source"] == "none"
    assert body["nodes"] == []
    assert body["edges"] == []
    assert body["message"]


def test_relationships_404s_for_unknown_book(client):
    res = client.get("/api/v1/books/does-not-exist/relationships")
    assert res.status_code == 404


def test_generate_is_honestly_not_available_offline(client):
    """conftest forces no Cloudflare credentials, so the real extractor
    isn't wired in -- generate must not pretend otherwise."""
    book = upload(client, make_minimal_pdf_bytes())
    res = client.post(f"/api/v1/books/{book['id']}/relationships/generate")
    assert res.status_code == 200
    assert res.json()["status"] == "not_available"


def test_generate_404s_for_unknown_book(client):
    res = client.post("/api/v1/books/does-not-exist/relationships/generate")
    assert res.status_code == 404


class _StubChatModel:
    status = "ok"
    name = "stub"

    def __init__(self, response_text: str):
        self._response_text = response_text

    async def complete(self, messages: list[dict], *, max_tokens: int) -> str:
        return self._response_text


class _ExplodingRetrieval:
    async def list_chunks(self, book_id, boundary, last_n=None):
        raise RuntimeError("boom")

    async def retrieve(self, *args, **kwargs):
        raise NotImplementedError


class _FakeRetrieval:
    def __init__(self, passages: list[RetrievedPassage]):
        self._passages = passages

    async def list_chunks(self, book_id, boundary, last_n=None):
        return self._passages

    async def retrieve(self, *args, **kwargs):
        raise NotImplementedError


def test_end_to_end_generate_then_cached_get(client):
    """Overrides the provider dependency with a stub model returning
    controlled JSON, so the full HTTP generate -> cache -> GET round trip is
    exercised without needing real Cloudflare credentials."""
    book = upload(client, make_minimal_pdf_bytes())
    passages = [_passage("c1", "Harry met Hagrid at the hut. Hagrid gave Harry a cake.")]

    response_json = json.dumps(
        {
            "characters": [
                {"name": "Harry", "role": "protagonist", "description": "a boy", "traits": ["brave"]},
                {"name": "Hagrid", "role": "ally", "description": "a giant"},
                {"name": "Voldemort", "role": "villain", "description": "not even mentioned here"},
            ],
            "relationships": [
                {
                    "source": "Harry",
                    "target": "Hagrid",
                    "relationship": "ally",
                    "label": "Hagrid gave Harry a cake",
                    "evidence": "Hagrid gave Harry a cake.",
                },
                {
                    "source": "Harry",
                    "target": "Voldemort",
                    "relationship": "enemy",
                    "label": "made up",
                    "evidence": "this quote does not exist in the text",
                },
            ],
        }
    )
    stub_provider = LLMCharacterGraphProvider(
        retrieval_provider=_FakeRetrieval(passages), chat_model=_StubChatModel(response_json)
    )
    client.app.dependency_overrides[get_character_graph_provider] = lambda: stub_provider
    try:
        res = client.post(f"/api/v1/books/{book['id']}/relationships/generate")
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["status"] == "ready"
        assert body["source"] == "extracted"
        names = {n["name"] for n in body["nodes"]}
        assert names == {"Harry", "Hagrid"}  # Voldemort: never mentioned in the text -> dropped
        assert len(body["edges"]) == 1  # the fabricated-evidence edge is dropped
        assert body["edges"][0]["relationship"] == "ally"
        assert body["generated_at"]

        # GET now returns the cached result, no model call needed.
        res = client.get(f"/api/v1/books/{book['id']}/relationships")
        assert res.json()["status"] == "ready"
        assert {n["name"] for n in res.json()["nodes"]} == {"Harry", "Hagrid"}
    finally:
        client.app.dependency_overrides.pop(get_character_graph_provider, None)


def test_generate_does_not_swallow_unexpected_retrieval_errors(client):
    """Unlike a bad/unparseable LLM response (handled gracefully -> "not
    available"), a genuine retrieval failure is a real bug and must not be
    silently turned into a fake "ready" result. TestClient re-raises it
    directly (for debugging); a real server returns 500 via the app's
    generic exception handler in app/core/errors.py."""
    book = upload(client, make_minimal_pdf_bytes())
    stub_provider = LLMCharacterGraphProvider(
        retrieval_provider=_ExplodingRetrieval(), chat_model=_StubChatModel("{}")
    )
    client.app.dependency_overrides[get_character_graph_provider] = lambda: stub_provider
    try:
        with pytest.raises(RuntimeError, match="boom"):
            client.post(f"/api/v1/books/{book['id']}/relationships/generate")
    finally:
        client.app.dependency_overrides.pop(get_character_graph_provider, None)


def test_offline_chat_model_never_gets_parsed_as_json():
    class _FakeOfflineModel:
        status = "fake"
        name = "offline"

        async def complete(self, messages, *, max_tokens):
            raise AssertionError("offline model should never be called")

    import asyncio

    provider = LLMCharacterGraphProvider(
        retrieval_provider=_FakeRetrieval([_passage("c1", "Some real book text.")]),
        chat_model=_FakeOfflineModel(),
    )
    result = asyncio.run(provider.get_graph("book-1", ReadingBoundary(book_id="book-1")))
    assert result.status == "not_available"


def test_normalize_drops_ungrounded_characters_and_relationships():
    passages = [_passage("c1", "Alice waved at Bob across the market square.")]
    raw = {
        "characters": [
            {"name": "Alice", "description": "a vendor"},
            {"name": "Charlie", "description": "never appears in the text"},
        ],
        "relationships": [
            {"source": "Alice", "target": "Charlie", "relationship": "friend", "evidence": "fabricated"},
        ],
    }
    nodes, edges = _normalize(raw, passages)
    assert [n["name"] for n in nodes] == ["Alice"]
    assert edges == []


def test_normalize_dedupes_same_character_mentioned_twice():
    passages = [_passage("c1", "Alice smiled. Alice waved.")]
    raw = {"characters": [{"name": "Alice"}, {"name": "alice"}], "relationships": []}
    nodes, _ = _normalize(raw, passages)
    assert len(nodes) == 1


def test_normalize_resolves_relationships_using_short_names():
    """Regression: the model listed full names in `characters` (e.g. "Albus
    Dumbledore") but short names in `relationships` (e.g. "Dumbledore") --
    exact-match lookup silently dropped every single edge."""
    passages = [
        _passage("c1", "Albus Dumbledore trusted Hagrid completely."),
        _passage("c2", "Hagrid said: I would trust Dumbledore with my life."),
    ]
    raw = {
        "characters": [
            {"name": "Albus Dumbledore", "role": "mentor"},
            {"name": "Hagrid", "role": "ally"},
        ],
        "relationships": [
            {
                "source": "Dumbledore",
                "target": "Hagrid",
                "relationship": "colleague",
                "evidence": "I would trust Dumbledore with my life.",
            }
        ],
    }
    nodes, edges = _normalize(raw, passages)
    assert {n["name"] for n in nodes} == {"Albus Dumbledore", "Hagrid"}
    assert len(edges) == 1
    assert edges[0]["source"] == "char_albus_dumbledore"
    assert edges[0]["target"] == "char_hagrid"


def test_normalize_treats_ambiguous_shared_name_word_as_unresolved():
    """Two different characters sharing a word in their name (e.g. two
    "Potter"s) must not let a short-name reference resolve to the wrong
    one -- or either one by guessing."""
    passages = [_passage("c1", "Harry Potter met James Potter in a vision.")]
    raw = {
        "characters": [{"name": "Harry Potter"}, {"name": "James Potter"}],
        "relationships": [
            {"source": "Potter", "target": "Harry Potter", "relationship": "family", "evidence": "a vision"}
        ],
    }
    nodes, edges = _normalize(raw, passages)
    assert len(nodes) == 2
    assert edges == []  # "Potter" alone is ambiguous between the two -> dropped, not guessed


def test_not_available_provider_returns_empty_graph():
    import asyncio

    result = asyncio.run(
        NotAvailableCharacterGraphProvider().get_graph("book-1", ReadingBoundary(book_id="book-1"))
    )
    assert result == GraphResult(book_id="book-1", status="not_available", nodes=[], edges=[], source="none")


def test_deleting_a_book_removes_its_character_graph_cache(client):
    book = upload(client, make_minimal_pdf_bytes())
    passages = [_passage("c1", "Alice waved at Bob.")]
    response_json = json.dumps({"characters": [{"name": "Alice"}], "relationships": []})
    stub_provider = LLMCharacterGraphProvider(
        retrieval_provider=_FakeRetrieval(passages), chat_model=_StubChatModel(response_json)
    )
    client.app.dependency_overrides[get_character_graph_provider] = lambda: stub_provider
    try:
        client.post(f"/api/v1/books/{book['id']}/relationships/generate")
    finally:
        client.app.dependency_overrides.pop(get_character_graph_provider, None)

    from app.db import database
    from app.models.character_graph import CharacterGraphCache

    with database.SessionLocal() as db:
        assert db.get(CharacterGraphCache, book["id"]) is not None

    res = client.delete(f"/api/v1/books/{book['id']}")
    assert res.status_code == 204

    with database.SessionLocal() as db:
        assert db.get(CharacterGraphCache, book["id"]) is None
