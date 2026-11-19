"""Character portraits: generated once per character, reused on every later
Update, generated only for characters new since the last Update."""
from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path

import httpx
import pytest

from app.api.deps import get_character_graph_provider, get_portrait_service
from app.core.config import get_settings
from app.integrations.character_graph import LLMCharacterGraphProvider, _normalize
from app.integrations.cloudflare import CloudflareClient, CloudflareError
from app.integrations.interfaces import RetrievedPassage
from app.integrations.portraits import build_portrait_prompt, scrub_names
from app.services.portrait_service import PortraitService
from tests.conftest import make_minimal_pdf_bytes, upload

CH1 = (
    "Mr. Dursley was a big, beefy man. Mrs. Dursley was thin and blonde. "
    "Their son Dudley was a large boy. Harry was small and skinny with untidy black hair."
)
CH5 = "Later, Harry and Dudley met Hagrid, a giant of a man with a wild tangled beard."


def _passage(text: str, index: int = 0) -> RetrievedPassage:
    return RetrievedPassage(
        book_id="b", chunk_id=f"c{index + 1}", text=text, source_location=f"page {index + 1}", order_index=index
    )


class _Retrieval:
    """Pages read so far. Each Update only analyzes pages added since the
    last one, so "reading on" means appending a new page via read_more()."""

    def __init__(self):
        self.pages = [CH1]

    def read_more(self, text: str) -> None:
        self.pages.append(text)

    async def list_chunks(self, book_id, boundary, last_n=None):
        return [_passage(text, i) for i, text in enumerate(self.pages)]

    async def retrieve(self, *args, **kwargs):
        raise NotImplementedError


class _ChatModel:
    status = "ok"
    name = "stub"

    def __init__(self):
        self.characters: list[dict] = []

    async def complete(self, messages, *, max_tokens):
        return json.dumps({"characters": self.characters, "relationships": []})


class _Generator:
    available = True

    def __init__(self):
        self.prompts: list[str] = []
        self.fail_next = 0

    async def generate(self, prompt: str) -> bytes:
        if self.fail_next:
            self.fail_next -= 1
            raise CloudflareError("Cloudflare API error 429: daily free allocation exceeded")
        self.prompts.append(prompt)
        return f"JPEG#{len(self.prompts)}".encode()


def _char(name: str, appearance: str = "") -> dict:
    return {"name": name, "role": "unknown", "description": "", "appearance": appearance}


@pytest.fixture()
def env(client):
    retrieval, chat, generator = _Retrieval(), _ChatModel(), _Generator()
    graph = LLMCharacterGraphProvider(retrieval_provider=retrieval, chat_model=chat)
    service = PortraitService(generator=generator, portraits_dir=get_settings().portraits_dir, concurrency=2)
    client.app.dependency_overrides[get_character_graph_provider] = lambda: graph
    client.app.dependency_overrides[get_portrait_service] = lambda: service
    book = upload(client, make_minimal_pdf_bytes(), title="Harry Potter and the Stone")
    try:
        yield client, book["id"], retrieval, chat, generator
    finally:
        client.app.dependency_overrides.clear()


def _update(client, book_id) -> dict:
    res = client.post(f"/api/v1/books/{book_id}/relationships/generate")
    assert res.status_code == 200, res.text
    return res.json()


def _nodes(client, book_id) -> dict[str, dict]:
    body = client.get(f"/api/v1/books/{book_id}/relationships").json()
    return {n["name"]: n for n in body["nodes"]}


def test_first_update_generates_a_portrait_for_every_character(env):
    client, book_id, _, chat, generator = env
    chat.characters = [_char("Harry", "a skinny boy with untidy black hair"), _char("Mr. Dursley", "a big beefy man")]
    body = _update(client, book_id)
    assert body["status"] == "ready"
    assert len(generator.prompts) == 2

    nodes = _nodes(client, book_id)
    for node in nodes.values():
        assert node["portrait_status"] == "ready"
        assert node["portrait_url"].startswith(f"/api/v1/books/{book_id}/characters/{node['id']}/portrait")

    img = client.get(nodes["Harry"]["portrait_url"])
    assert img.status_code == 200
    assert img.headers["content-type"] == "image/jpeg"
    assert img.content.startswith(b"JPEG#")


def test_later_update_reuses_existing_portraits_and_only_generates_new_characters(env):
    client, book_id, retrieval, chat, generator = env
    chat.characters = [_char("Harry", "a skinny boy"), _char("Dudley", "a large boy")]
    _update(client, book_id)
    first = _nodes(client, book_id)
    harry_bytes = client.get(first["Harry"]["portrait_url"]).content
    assert len(generator.prompts) == 2

    # Reader moves on; a later chapter introduces Hagrid and describes Harry more.
    retrieval.read_more(CH5)
    chat.characters = [
        _char("Harry", "a skinny boy with a lightning scar and round glasses"),
        _char("Dudley", "a large boy"),
        _char("Hagrid", "a giant man with a wild tangled beard"),
    ]
    _update(client, book_id)
    assert len(generator.prompts) == 3  # only Hagrid
    assert "beard" in generator.prompts[-1]

    second = _nodes(client, book_id)
    assert second["Harry"]["portrait_url"] == first["Harry"]["portrait_url"]
    assert client.get(second["Harry"]["portrait_url"]).content == harry_bytes  # same picture
    assert second["Hagrid"]["portrait_status"] == "ready"


def test_name_variant_reuses_the_same_portrait(env):
    client, book_id, retrieval, chat, generator = env
    chat.characters = [_char("Dudley", "a large boy")]
    _update(client, book_id)
    retrieval.read_more("Dudley Dursley kicked his mother all the way down the street.")
    chat.characters = [_char("Dudley Dursley", "a large boy")]
    _update(client, book_id)
    assert len(generator.prompts) == 1
    node = _nodes(client, book_id)["Dudley Dursley"]
    # The character map itself now merges the variant into the existing
    # character and keeps its id; either way it must be the same portrait.
    assert node["id"] in {"char_dudley", "char_dudley_dursley"}
    assert node["portrait_status"] == "ready"
    assert client.get(node["portrait_url"]).status_code == 200  # alias id resolves


def test_mr_and_mrs_never_share_a_portrait_and_ambiguous_name_gets_its_own(env):
    client, book_id, retrieval, chat, generator = env
    chat.characters = [_char("Mr. Dursley", "a big man"), _char("Mrs. Dursley", "a thin woman")]
    _update(client, book_id)
    assert len(generator.prompts) == 2

    retrieval.read_more("A Dursley neighbour peered over the hedge.")
    chat.characters = [_char("Dursley", "someone")]  # matches both -> don't guess
    _update(client, book_id)
    assert len(generator.prompts) == 3


def test_prompt_never_contains_character_names_or_book_title(env):
    client, book_id, _, chat, generator = env
    chat.characters = [
        _char("Harry", "Harry, a skinny boy, son of the Potters"),
        _char("Dudley", "Dudley's large cousin-like frame, from Harry Potter and the Stone"),
    ]
    _update(client, book_id)
    for prompt in generator.prompts:
        lower = prompt.lower()
        for word in ("harry", "potter", "dudley", "stone"):
            assert word not in lower, prompt
    assert "skinny boy" in generator.prompts[0] or "skinny boy" in generator.prompts[1]


def test_failed_portrait_is_retried_on_next_update_without_failing_the_update(env):
    client, book_id, _, chat, generator = env
    chat.characters = [_char("Harry", "a skinny boy")]
    generator.fail_next = 1
    body = _update(client, book_id)
    assert body["status"] == "ready"
    node = _nodes(client, book_id)["Harry"]
    assert node["portrait_status"] == "failed"
    assert node["portrait_url"] is None
    assert client.get(f"/api/v1/books/{book_id}/characters/char_harry/portrait").status_code == 404

    _update(client, book_id)
    assert _nodes(client, book_id)["Harry"]["portrait_status"] == "ready"


def test_portrait_endpoint_404s_for_unknown_character_and_book(env):
    client, book_id, *_ = env
    assert client.get(f"/api/v1/books/{book_id}/characters/char_nobody/portrait").status_code == 404
    assert client.get("/api/v1/books/nope/characters/char_harry/portrait").status_code == 404


def test_deleting_a_book_removes_portrait_rows_and_files(env):
    client, book_id, _, chat, _ = env
    chat.characters = [_char("Harry", "a skinny boy")]
    _update(client, book_id)
    folder = Path(get_settings().portraits_dir) / book_id
    assert any(folder.iterdir())

    assert client.delete(f"/api/v1/books/{book_id}").status_code == 204

    from app.db import database
    from app.models.character_portrait import CharacterPortrait

    with database.SessionLocal() as db:
        assert db.query(CharacterPortrait).filter_by(book_id=book_id).count() == 0
    assert not folder.exists()


def test_offline_update_shows_no_portraits(client):
    """No Cloudflare credentials: the real portrait service has no image
    model, so nodes just report "none" and the UI keeps its icons."""
    graph = LLMCharacterGraphProvider(retrieval_provider=_Retrieval(), chat_model=_ChatModel())
    graph.chat_model.characters = [_char("Harry", "a skinny boy")]
    client.app.dependency_overrides[get_character_graph_provider] = lambda: graph
    try:
        book = upload(client, make_minimal_pdf_bytes())
        body = client.post(f"/api/v1/books/{book['id']}/relationships/generate").json()
        assert body["status"] == "ready"
        assert body["nodes"][0]["portrait_status"] == "none"
        assert body["nodes"][0]["portrait_url"] is None
    finally:
        client.app.dependency_overrides.clear()


# ---- unit tests ------------------------------------------------------------


def test_normalize_keeps_appearance():
    nodes, _ = _normalize({"characters": [_char("Harry", "a skinny boy")]}, [_passage(CH1)])
    assert nodes[0]["appearance"] == "a skinny boy"


def test_scrub_names_handles_possessives_and_plurals():
    text = scrub_names("Harry's cousin, son of the Potters, a big boy", ["Harry Potter"])
    assert "harry" not in text.lower() and "potter" not in text.lower()
    assert "big boy" in text


def test_prompt_falls_back_when_appearance_is_empty_or_only_names():
    assert "an ordinary adult person" in build_portrait_prompt("", names=["Harry"])
    assert "an ordinary adult person" in build_portrait_prompt("Harry", names=["Harry"])


def _cf_client(handler):
    async def no_sleep(_):
        return None

    return CloudflareClient("acct", "tok", transport=httpx.MockTransport(handler), sleep=no_sleep, max_retries=0)


def test_cloudflare_generate_image_decodes_base64_and_sends_payload():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"success": True, "result": {"image": base64.b64encode(b"jpg").decode()}})

    client = _cf_client(handler)
    data = asyncio.run(client.generate_image("@cf/black-forest-labs/flux-1-schnell", "a boy", steps=8))
    assert data == b"jpg"
    assert seen["url"].endswith("/accounts/acct/ai/run/@cf/black-forest-labs/flux-1-schnell")
    assert seen["body"] == {"prompt": "a boy", "steps": 8}  # no extra keys: the live schema rejects them


@pytest.mark.parametrize("result", [{}, {"image": ""}, {"image": "not base64!!"}])
def test_cloudflare_generate_image_rejects_missing_or_invalid_image(result):
    client = _cf_client(lambda request: httpx.Response(200, json={"success": True, "result": result}))
    with pytest.raises(CloudflareError):
        asyncio.run(client.generate_image("@cf/x/y", "a boy"))
