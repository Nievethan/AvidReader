"""Scene pictures: the reader taps Illustrate on a page and gets a picture of
its key moment -- made once, reused after, never shown before the reader
reaches that page."""
from __future__ import annotations

import asyncio
import json

import pytest

from app.api.deps import get_scene_service
from app.core.config import get_settings
from app.integrations.cloudflare import CloudflareError
from app.integrations.interfaces import RetrievedPassage
from app.integrations.scenes import LLMScenePicker, build_scene_prompt, ground_scenes
from app.services.scene_service import SceneService
from tests.conftest import make_minimal_pdf_bytes, upload

PAGES = [
    "Dorothy lived in the midst of the great Kansas prairies with Uncle Henry and Aunt Em.",
    "From the far north Dorothy heard a low wail of the wind, and the cyclone carried the house away.",
    "The house fell very gently in the midst of a country of marvelous beauty.",
    "She saw a Scarecrow perched on a pole, and one of its eyes slowly winked at her.",
]


def _passage(index: int) -> RetrievedPassage:
    return RetrievedPassage(
        book_id="b", chunk_id=f"c{index + 1}", text=PAGES[index], source_location=f"page {index + 1}",
        order_index=index, page_start=index + 1, page_end=index + 1,
    )


class _Retrieval:
    """Stands in for Qdrant: only returns pages up to the boundary."""

    async def list_chunks(self, book_id, boundary, last_n=None):
        limit = boundary.limit
        return [_passage(i) for i in range(len(PAGES)) if limit is None or i + 1 <= limit]

    async def retrieve(self, *args, **kwargs):
        raise NotImplementedError


class _ChatModel:
    """Picks the page it is shown, quoting its first eight words."""

    status = "ok"
    name = "stub"

    def __init__(self):
        self.fail_next = 0
        self.invent_quote = False
        self.prompts: list[str] = []

    async def complete(self, messages, *, max_tokens):
        if self.fail_next:
            self.fail_next -= 1
            raise CloudflareError("Cloudflare API error 429")
        prompt = messages[-1]["content"]
        self.prompts.append(prompt)
        page = next(p for p in PAGES if p in prompt)
        quote = "a dragon breathed fire" if self.invent_quote else " ".join(page.split()[:8])
        return json.dumps({"scenes": [{
            "title": f"Moment {PAGES.index(page) + 1}",
            "caption": "Something happens.",
            "visual": "Dorothy, a girl in a gingham dress, stands on the prairie",
            "evidence": quote,
        }]})


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
        await asyncio.sleep(0)
        return f"JPEG#{len(self.prompts)}".encode()


@pytest.fixture()
def env(client):
    chat, generator = _ChatModel(), _Generator()
    service = SceneService(
        picker=LLMScenePicker(chat), generator=generator, retrieval_provider=_Retrieval(),
        scenes_dir=get_settings().scenes_dir,
    )
    client.app.dependency_overrides[get_scene_service] = lambda: service
    book = upload(client, make_minimal_pdf_bytes(), title="The Wonderful Wizard of Oz")
    try:
        yield client, book["id"], chat, generator, service
    finally:
        client.app.dependency_overrides.clear()


def _open_page(client, book_id, page: int) -> None:
    """The reader shows `page` (1-based); Flutter saves it 0-based."""
    res = client.put(f"/api/v1/books/{book_id}/progress", json={"current_page": page - 1})
    assert res.status_code == 200, res.text


def _illustrate(client, book_id, page: int) -> dict:
    res = client.post(f"/api/v1/books/{book_id}/scenes/at/{page}")
    assert res.status_code == 200, res.text
    return res.json()


def _gallery(client, book_id) -> list[dict]:
    res = client.get(f"/api/v1/books/{book_id}/scenes")
    assert res.status_code == 200, res.text
    return res.json()["scenes"]


# ---- pure helpers ------------------------------------------------------------


def test_ground_scenes_drops_invented_quotes_and_keeps_reading_order():
    passages = [_passage(i) for i in range(4)]
    raw = {"scenes": [
        {"title": "Scarecrow", "visual": "a straw man on a pole", "evidence": "one of its eyes slowly winked"},
        {"title": "Fake", "visual": "a dragon", "evidence": "a dragon breathed fire on the castle"},
        {"title": "Cyclone", "visual": "a house in the sky", "evidence": "the cyclone carried the house away"},
        {"title": "", "visual": "missing title", "evidence": "Uncle Henry and Aunt Em"},
    ]}
    picked = ground_scenes(raw, passages, max_scenes=5)
    assert [s.title for s in picked] == ["Cyclone", "Scarecrow"]
    assert picked[0].passage.page_start == 2
    assert "Dorothy" in picked[0].names and "Scarecrow" in picked[0].names
    assert "From" not in picked[0].names  # sentence-initial words aren't names


def test_ground_scenes_handles_garbage_shapes():
    assert ground_scenes({}, [_passage(0)], 3) == []
    assert ground_scenes({"scenes": "nope"}, [_passage(0)], 3) == []
    assert ground_scenes({"scenes": [1, None, "x"]}, [_passage(0)], 3) == []


def test_scene_prompt_is_storybook_styled_and_name_free():
    prompt = build_scene_prompt(
        "Dorothy and Toto from the Wizard of Oz stand on the yellow road",
        names=["Dorothy", "Toto"], book_title="The Wonderful Wizard of Oz",
    )
    lower = prompt.lower()
    for word in ("dorothy", "toto", "wizard", "wonderful"):
        assert word not in lower, prompt
    assert "storybook illustration" in lower
    assert "yellow road" in lower
    assert "no text" in lower


# ---- the Illustrate button -----------------------------------------------------


def test_illustrate_paints_the_current_page_and_serves_it(env):
    client, book_id, chat, generator, _ = env
    _open_page(client, book_id, 2)
    body = _illustrate(client, book_id, 2)
    assert body["status"] == "ready"
    scene = body["scene"]
    assert scene["source_location"] == "page 2" and scene["title"] == "Moment 2"
    assert PAGES[1] in chat.prompts[0] and PAGES[0] not in chat.prompts[0]  # only that page is sent
    assert "storybook" in generator.prompts[0] and "dorothy" not in generator.prompts[0].lower()

    img = client.get(scene["image_url"])
    assert img.status_code == 200
    assert img.headers["content-type"] == "image/jpeg"
    assert img.content == b"JPEG#1"


def test_second_tap_returns_the_saved_picture_without_model_calls(env):
    client, book_id, chat, generator, _ = env
    _open_page(client, book_id, 1)
    first = _illustrate(client, book_id, 1)
    second = _illustrate(client, book_id, 1)
    assert second["scene"] == first["scene"]
    assert len(chat.prompts) == 1 and len(generator.prompts) == 1


def test_cannot_illustrate_a_page_not_reached(env):
    client, book_id, chat, generator, _ = env
    body = _illustrate(client, book_id, 1)  # no progress saved yet
    assert body["status"] == "not_available" and "haven't reached" in body["message"]
    _open_page(client, book_id, 2)
    body = _illustrate(client, book_id, 3)
    assert body["status"] == "not_available"
    assert chat.prompts == [] and generator.prompts == []
    assert client.post(f"/api/v1/books/{book_id}/scenes/at/0").status_code == 422


def test_gallery_lists_reached_scenes_and_hides_later_ones(env):
    client, book_id, _, _, _ = env
    _open_page(client, book_id, 4)
    for page in (4, 1, 3):
        _illustrate(client, book_id, page)
    assert [s["source_location"] for s in _gallery(client, book_id)] == ["page 1", "page 3", "page 4"]

    page4 = _gallery(client, book_id)[-1]
    _open_page(client, book_id, 2)  # reader went back
    assert [s["source_location"] for s in _gallery(client, book_id)] == ["page 1"]
    assert client.get(page4["image_url"]).status_code == 404  # spoiler gate on the file too


def test_empty_gallery_explains_the_button(env):
    client, book_id, _, _, _ = env
    body = client.get(f"/api/v1/books/{book_id}/scenes").json()
    assert body["status"] == "not_available" and "Illustrate" in body["message"]


def test_failed_painting_is_retried_on_next_tap_from_the_saved_prompt(env):
    client, book_id, chat, generator, _ = env
    _open_page(client, book_id, 1)
    generator.fail_next = 1
    body = _illustrate(client, book_id, 1)
    assert body["status"] == "failed" and body["scene"]["image_url"] is None

    body = _illustrate(client, book_id, 1)
    assert body["status"] == "ready"
    assert len(chat.prompts) == 1  # moment not re-picked


def test_ai_error_and_invented_quote_save_nothing(env):
    client, book_id, chat, generator, _ = env
    _open_page(client, book_id, 1)
    chat.fail_next = 1
    body = _illustrate(client, book_id, 1)
    assert body["status"] == "not_available" and "error" in body["message"]

    chat.invent_quote = True
    body = _illustrate(client, book_id, 1)
    assert body["status"] == "not_available" and "Couldn't find a moment" in body["message"]
    assert generator.prompts == [] and _gallery(client, book_id) == []

    chat.invent_quote = False
    assert _illustrate(client, book_id, 1)["status"] == "ready"


def test_double_tap_paints_once(env):
    client, book_id, chat, generator, service = env
    _open_page(client, book_id, 2)

    async def both():
        from app.api.v1.scenes import scene_boundary
        from app.db import database
        from app.repositories import book_repository

        with database.SessionLocal() as db1, database.SessionLocal() as db2:
            book = book_repository.get_book(db1, book_id)
            boundary, unit = scene_boundary(db1, book)
            return await asyncio.gather(
                service.illustrate(db1, book_id, 2, boundary, unit=unit),
                service.illustrate(db2, book_id, 2, boundary, unit=unit),
            )

    first, second = asyncio.run(both())
    assert first.status == second.status == "ready"
    assert len(chat.prompts) == 1 and len(generator.prompts) == 1


def test_offline_backend_says_so(client):
    book_id = upload(client, make_minimal_pdf_bytes())["id"]
    _open_page(client, book_id, 1)
    body = client.post(f"/api/v1/books/{book_id}/scenes/at/1").json()
    assert body["status"] == "not_available"
    assert "Cloudflare" in body["message"]


def test_deleting_a_book_removes_its_scenes(env):
    client, book_id, _, _, _ = env
    _open_page(client, book_id, 1)
    _illustrate(client, book_id, 1)
    folder = get_settings().scenes_dir / book_id
    assert folder.is_dir()
    assert client.delete(f"/api/v1/books/{book_id}").status_code in (200, 204)
    assert not folder.exists()
