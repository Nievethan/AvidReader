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
from app.integrations.character_graph import LLMCharacterGraphProvider, _normalize, merge_graph
from app.integrations.cloudflare import CloudflareClient, CloudflareError
from app.integrations.interfaces import RetrievedPassage
from app.integrations.portraits import build_portrait_prompt, meaningful_appearance, scrub_names
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
        self.nsfw_next = 0  # reject this many calls with Cloudflare's NSFW error
        self.calls = 0

    async def generate(self, prompt: str) -> bytes:
        self.calls += 1
        if self.nsfw_next:
            self.nsfw_next -= 1
            raise CloudflareError("Cloudflare API error 400: AiError: AiError: Input prompt contains NSFW content.")
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
    # min_details=0: these tests are about reuse/matching, not the "too little
    # description" rule (covered separately below), so every character is painted.
    service = PortraitService(
        generator=generator, portraits_dir=get_settings().portraits_dir, concurrency=2, min_details=0
    )
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


# ---- portrait prompt bug fixes (Game of Thrones findings) -------------------

GOT_NAMES = [
    "The man", "The woman", "The killer", "Maester Luwin", "Septa Mordane", "Old Nan",
    "Jaime Lannister", "Hodor", "Lady Arryn", "Ser Boros",
]


@pytest.mark.parametrize(
    ("appearance", "must_keep"),
    [
        ("a small grey man with a heavy chain around his neck", "small grey man with a heavy chain"),
        ("a bony woman with sharp eyes and a thin mouth", "bony woman with sharp eyes"),
        ("an old woman", "an old woman"),
        ("a man with a foul stench, like a killer", "a man with a foul stench, like a killer"),
    ],
)
def test_generic_characters_never_scrub_common_words(appearance, must_keep):
    """Regression: "The man" / "The woman" / "The killer" were listed as
    characters, so "man", "woman" and "killer" were stripped from EVERY prompt
    (Maester Luwin became a grey dog, Septa Mordane a skeleton)."""
    prompt = build_portrait_prompt(appearance, names=GOT_NAMES, book_title="A Game of Thrones")
    assert must_keep in prompt


def test_real_proper_names_are_still_scrubbed():
    prompt = build_portrait_prompt(
        "Hodor, a huge stableboy who serves Jaime Lannister's family in a Game of Thrones",
        names=GOT_NAMES, book_title="A Game of Thrones",
    )
    for word in ("hodor", "jaime", "lannister", "thrones"):
        assert word not in prompt.lower(), prompt
    assert "huge stableboy" in prompt


@pytest.mark.parametrize(
    "value",
    ["not described directly", "Not described.", "Appearance not described", "not mentioned",
     "unknown", "N/A", "none", "No description given", "", None],
)
def test_non_answers_are_not_appearances(value):
    assert meaningful_appearance(value) is None
    assert "an ordinary adult person" in build_portrait_prompt(value, names=GOT_NAMES)


@pytest.mark.parametrize("value", ["a man, not described further than his scar", "an old woman", "tall, golden hair"])
def test_real_descriptions_are_kept(value):
    assert meaningful_appearance(value) == value


def test_normalize_drops_non_answer_appearance():
    nodes, _ = _normalize({"characters": [_char("Harry", "not described directly")]}, [_passage(CH1)])
    assert nodes[0]["appearance"] is None


def test_merge_graph_takes_appearance_from_a_later_batch():
    """Regression: a character named in batch 1 but only described in batch 3
    kept "no appearance" forever (merge only updated description/role)."""
    base = [{"id": "char_hodor", "name": "Hodor", "role": "minor", "description": "", "appearance": None}]
    later = [{"id": "char_hodor", "name": "Hodor", "role": "minor", "description": "",
              "appearance": "a giant of a man, slow and gentle, in a stableboy's tunic"}]
    nodes, _ = merge_graph(base, [], later, [])
    assert nodes[0]["appearance"] == "a giant of a man, slow and gentle, in a stableboy's tunic"


def test_merge_graph_keeps_richer_appearance_and_ignores_non_answers():
    base = [{"id": "char_robb", "name": "Robb", "appearance": "a tall boy with auburn hair and blue eyes"}]
    nodes, _ = merge_graph(base, [], [{"id": "char_robb", "name": "Robb", "appearance": "red cheeks"}], [])
    assert nodes[0]["appearance"] == "a tall boy with auburn hair and blue eyes"
    nodes, _ = merge_graph(base, [], [{"id": "char_robb", "name": "Robb", "appearance": "not described directly"}], [])
    assert nodes[0]["appearance"] == "a tall boy with auburn hair and blue eyes"


def test_safe_prompt_drops_flagged_words_and_adds_clothing():
    prompt = build_portrait_prompt("beautiful, golden hair, green eyes", names=GOT_NAMES, safe=True)
    assert "beautiful" not in prompt.lower()
    assert "skin texture" not in prompt
    assert "fully clothed in period costume" in prompt
    assert "golden hair, green eyes" in prompt


def test_nsfw_false_positive_is_retried_once_with_softened_prompt(env):
    client, book_id, _, chat, generator = env
    chat.characters = [_char("Harry", "beautiful, small and skinny boy")]
    generator.nsfw_next = 1
    _update(client, book_id)
    assert generator.calls == 2
    assert "fully clothed in period costume" in generator.prompts[0]
    assert "beautiful" not in generator.prompts[0].lower()
    assert _nodes(client, book_id)["Harry"]["portrait_status"] == "ready"


def test_repeated_nsfw_rejection_is_skipped_and_never_retried(env):
    client, book_id, retrieval, chat, generator = env
    chat.characters = [_char("Harry", "beautiful, small and skinny boy")]
    generator.nsfw_next = 2
    body = _update(client, book_id)
    assert body["status"] == "ready"  # the Update itself still succeeds
    assert generator.calls == 2
    node = _nodes(client, book_id)["Harry"]
    assert node["portrait_status"] == "skipped"
    assert node["portrait_url"] is None

    retrieval.read_more("Harry was small and skinny, and he ran.")
    _update(client, book_id)
    assert generator.calls == 2  # not retried on later Updates
    assert _nodes(client, book_id)["Harry"]["portrait_status"] == "skipped"


def test_other_errors_still_retry_on_next_update(env):
    """Only the safety filter is final; a rate limit stays "failed" and retries."""
    client, book_id, retrieval, chat, generator = env
    chat.characters = [_char("Harry", "a skinny boy")]
    generator.fail_next = 1
    _update(client, book_id)
    assert generator.calls == 1  # no softened retry for non-NSFW errors
    assert _nodes(client, book_id)["Harry"]["portrait_status"] == "failed"
    retrieval.read_more("Harry was small and skinny, and he ran.")
    _update(client, book_id)
    assert _nodes(client, book_id)["Harry"]["portrait_status"] == "ready"


# ---- structured look profiles, setting, description pass (B5-B9) ------------

from app.integrations import character_graph as cg  # noqa: E402
from app.integrations.character_looks import (  # noqa: E402
    build_subject,
    merge_looks,
    normalize_look,
    sex_from_name,
)
from app.integrations.interfaces import ReadingBoundary  # noqa: E402
from app.integrations.portraits import CharacterDescriber, select_passages  # noqa: E402


def test_extraction_prompt_has_one_shape_with_look_and_setting():
    """Regression: a merge left TWO JSON shapes in the prompt (the second
    without appearance) and run-together instructions."""
    assert cg._REQUIRED_SHAPE.count('"characters"') == 1
    assert '"look"' in cg._REQUIRED_SHAPE and '"setting"' in cg._REQUIRED_SHAPE
    user = cg._build_messages([_passage(CH1)])[1]["content"]
    assert user.count("Output JSON only.") == 1


def test_normalize_look_cleans_values():
    look = normalize_look({"sex": "Male", "age": "not described", "hair": "golden", "eyes": "N/A", "junk": "x"})
    assert look == {"type": "human", "sex": "man", "hair": "golden"}
    assert normalize_look({"species": "direwolf", "hair": "white"})["type"] == "animal"
    assert normalize_look({"sex": "unknown"}) is None
    assert normalize_look("a man") is None


def test_merge_looks_primary_wins_and_fallback_fills_gaps():
    merged = merge_looks({"sex": "man", "hair": "golden"}, {"sex": "woman", "eyes": "green", "hair": "brown"})
    assert merged == {"sex": "man", "hair": "golden", "eyes": "green"}


@pytest.mark.parametrize(
    ("name", "sex"),
    [("Ser Boros", "man"), ("Septa Mordane", "woman"), ("Lady Arryn", "woman"), ("Maester Luwin", "man"),
     ("Old Nan", None), ("Hodor", None)],
)
def test_sex_from_titles(name, sex):
    assert sex_from_name(name) == sex


@pytest.mark.parametrize(
    ("name", "look", "appearance", "expected"),
    [
        ("Jaime Lannister", {"sex": "man", "age": "young adult", "build": "tall", "hair": "golden", "eyes": "green"},
         None, "a tall young adult man with golden hair, green eyes"),
        ("Ghost", {"type": "animal", "species": "direwolf", "hair": "white", "eyes": "red"},
         None, "a direwolf with white fur, red eyes"),
        ("Robb", {"sex": "boy", "age": "fourteen", "hair": "auburn"}, None, "a fourteen-year-old boy with auburn hair"),
        ("Ser Boros", None, None, "a man"),
        ("Septa Mordane", None, "a bony woman with sharp eyes", "a bony woman with sharp eyes"),
        ("Catelyn", None, None, "an ordinary adult person"),
        ("Eddard Stark", {"sex": "man", "age": "in his mid-thirties", "hair": "long brown", "clothing": "cloak and furs"},
         None, "a man in his mid-thirties with long brown hair, wearing cloak and furs"),
    ],
)
def test_build_subject_always_names_who_is_drawn(name, look, appearance, expected):
    assert build_subject(normalize_look(look) if look else None, appearance, name) == expected


def test_dwarf_is_drawn_as_an_adult():
    subject = build_subject(normalize_look({"sex": "man", "build": "dwarf"}), None, "Tyrion")
    assert "adult man with dwarfism and an adult face" in subject
    assert "child" not in subject and "boy" not in subject


def test_comparisons_and_horses_are_cleaned():
    joffrey = build_subject(normalize_look({"sex": "boy", "age": "twelve years old", "build": "taller than Jon Snow"}),
                            None, "Joffrey")
    assert joffrey == "a tall twelve-year-old boy"
    will = build_subject(normalize_look({"sex": "man", "age": "young", "distinctive": "with a shaggy garron",
                                         "clothing": "a cloak, riding a pony"}), None, "Will")
    assert "garron" not in will and "pony" not in will and "riding" not in will
    assert will.startswith("a young man")


def test_prompt_includes_setting_scrubbed_and_animal_framing():
    prompt = build_portrait_prompt(
        None, names=["Ghost", "Winterfell"], look=normalize_look({"species": "direwolf", "hair": "white"}),
        setting="medieval fantasy kingdom, the cold castle of Winterfell", name="Ghost",
    )
    assert "in a setting of medieval fantasy kingdom, the cold castle of" in prompt
    assert "Winterfell" not in prompt
    assert prompt.startswith("Wildlife film still: a direwolf with white fur")


def test_normalize_stores_look_and_rendered_appearance():
    entry = {"name": "Harry", "look": {"sex": "boy", "build": "small and skinny", "hair": "untidy black"}}
    nodes, _ = _normalize({"characters": [entry]}, [_passage(CH1)])
    assert nodes[0]["look"]["sex"] == "boy"
    assert nodes[0]["appearance"] == "a small and skinny boy with untidy black hair"


def test_merge_graph_merges_look_field_by_field():
    base = [{"id": "char_harry", "name": "Harry", "look": {"type": "human", "sex": "boy"}}]
    new = [{"id": "char_harry", "name": "Harry", "look": {"type": "human", "hair": "untidy black"}}]
    nodes, _ = merge_graph(base, [], new, [])
    assert nodes[0]["look"] == {"type": "human", "sex": "boy", "hair": "untidy black"}
    assert nodes[0]["appearance"] == "a boy with untidy black hair"


def test_setting_is_extracted_once_and_kept(env):
    client, book_id, retrieval, chat, _ = env

    class _SettingChat(_ChatModel):
        def __init__(self):
            super().__init__()
            self.setting = "quiet English suburb, present day"

        async def complete(self, messages, *, max_tokens):
            return json.dumps({"setting": self.setting, "characters": self.characters, "relationships": []})

    setting_chat = _SettingChat()
    graph = LLMCharacterGraphProvider(retrieval_provider=retrieval, chat_model=setting_chat)
    client.app.dependency_overrides[get_character_graph_provider] = lambda: graph
    setting_chat.characters = [_char("Harry", "a skinny boy")]
    assert _update(client, book_id)["setting"] == "quiet English suburb, present day"

    setting_chat.setting = "a castle in the mountains"  # later batches don't change it
    retrieval.read_more("Harry was small and skinny, and he ran.")
    _update(client, book_id)
    body = client.get(f"/api/v1/books/{book_id}/relationships").json()
    assert body["setting"] == "quiet English suburb, present day"


# -- description pass --

def test_select_passages_prefers_mentions_and_keeps_reading_order():
    passages = [
        _passage("Robb laughed in the yard.", 0),
        _passage("Jaime Lannister was tall, with golden hair and green eyes.", 1),
        _passage("Nobody else here.", 2),
        _passage("Jaime smiled at the king.", 3),
    ]
    chosen = select_passages("Jaime Lannister", passages, max_chars=10_000)
    assert [p.order_index for p in chosen] == [1, 3]
    assert select_passages("The man", passages, max_chars=10_000) == []
    assert len(select_passages("Jaime Lannister", passages, max_chars=10)) == 1  # best one only


class _DescribeChat:
    status = "ok"
    name = "describe-stub"

    def __init__(self, look: dict | None = None, fail: bool = False):
        self.look = look or {}
        self.fail = fail
        self.calls: list[str] = []

    async def complete(self, messages, *, max_tokens):
        self.calls.append(messages[1]["content"])
        if self.fail:
            raise CloudflareError("Cloudflare API error 500")
        return json.dumps({"look": self.look})


def test_describer_returns_look_or_none():
    retrieval = _Retrieval()
    chat = _DescribeChat({"sex": "woman", "hair": "blonde", "age": "not described"})
    describer = CharacterDescriber(chat_model=chat, retrieval_provider=retrieval)
    boundary = ReadingBoundary(book_id="b")
    look = asyncio.run(describer.describe("b", "Mrs. Dursley", boundary))
    assert look == {"type": "human", "sex": "woman", "hair": "blonde"}
    assert 'called "Mrs. Dursley"' in chat.calls[0]
    assert asyncio.run(describer.describe("b", "Nobody Here", boundary)) is None  # no passages, no call
    assert len(chat.calls) == 1
    failing = CharacterDescriber(chat_model=_DescribeChat(fail=True), retrieval_provider=retrieval)
    assert asyncio.run(failing.describe("b", "Mrs. Dursley", boundary)) is None


@pytest.fixture()
def env_with_describer(env):
    client, book_id, retrieval, chat, generator = env
    describe_chat = _DescribeChat({"sex": "woman", "build": "thin", "hair": "blonde", "eyes": "pale"})
    service = PortraitService(
        generator=generator,
        portraits_dir=get_settings().portraits_dir,
        describer=CharacterDescriber(chat_model=describe_chat, retrieval_provider=retrieval),
        min_details=0,
    )
    client.app.dependency_overrides[get_portrait_service] = lambda: service
    return client, book_id, retrieval, chat, generator, describe_chat


def test_description_pass_shapes_the_prompt_once_per_new_character(env_with_describer):
    client, book_id, retrieval, chat, generator, describe_chat = env_with_describer
    chat.characters = [{"name": "Mrs. Dursley", "look": {"hair": "blonde"}}]
    _update(client, book_id)
    assert len(describe_chat.calls) == 1
    assert "a thin woman with blonde hair, pale eyes" in generator.prompts[0]
    assert "Dursley" not in generator.prompts[0]

    retrieval.read_more("Mrs. Dursley craned over the fence again.")
    _update(client, book_id)
    assert len(describe_chat.calls) == 1  # existing portrait reused: no second description call

    from app.db import database
    from app.models.character_portrait import CharacterPortrait

    with database.SessionLocal() as db:
        row = db.query(CharacterPortrait).filter_by(book_id=book_id).one()
        assert json.loads(row.look_json)["sex"] == "woman"  # the profile it was painted from


def test_description_pass_failure_falls_back_to_map_profile(env_with_describer):
    client, book_id, _, chat, generator, describe_chat = env_with_describer
    describe_chat.fail = True
    chat.characters = [{"name": "Harry", "look": {"sex": "boy", "hair": "untidy black"}}]
    _update(client, book_id)
    assert "a boy with untidy black hair" in generator.prompts[0]
    assert _nodes(client, book_id)["Harry"]["portrait_status"] == "ready"


# ---- prompt styles (C), who gets a portrait (D14), titled duplicates (D15),
# ---- one-time placeholder upgrades (E16) -----------------------------------

from app.integrations.character_looks import detail_count, titled_variant  # noqa: E402

_JAIME = normalize_look({"sex": "man", "build": "tall", "hair": "golden"})


def test_cinematic_prompt_has_no_studio_cues_and_positive_wording():
    prompt = build_portrait_prompt(None, names=[], look=_JAIME, setting="cold northern castle")
    assert prompt.startswith("Cinematic film still from a period drama: a tall man with golden hair")
    for studio in ("window light", "85mm", "plain muted background", "skin texture"):
        assert studio not in prompt
    for negative in ("No text", "no watermark", "Not a celebrity"):
        assert negative not in prompt
    assert "softly blurred background of cold northern castle" in prompt
    assert "wearing clothing that fits the story's time and place" in prompt
    assert "unknown actor" in prompt and "clean frame" in prompt


def test_clothing_from_profile_replaces_the_generic_clothing_clause():
    look = normalize_look({"sex": "man", "hair": "dark", "clothing": "black leather and ringmail"})
    prompt = build_portrait_prompt(None, names=[], look=look)
    assert "wearing black leather and ringmail" in prompt
    assert "fits the story's time and place" not in prompt


def test_painted_style_and_animal_templates():
    painted = build_portrait_prompt(None, names=[], look=_JAIME, style="painted")
    assert painted.startswith("Oil-painted fantasy book portrait of a tall man")
    wolf = normalize_look({"species": "direwolf", "hair": "white"})
    assert build_portrait_prompt(None, names=[], look=wolf).startswith("Wildlife film still: a direwolf")
    assert build_portrait_prompt(None, names=[], look=wolf, style="painted").startswith("Oil painting of a direwolf")
    assert "in its natural surroundings" in build_portrait_prompt(None, names=[], look=wolf)
    # unknown style falls back to the default
    assert build_portrait_prompt(None, names=[], look=_JAIME, style="anime").startswith("Cinematic film still")


def test_detail_count_and_titled_variants():
    assert detail_count({"sex": "man"}) == 0
    assert detail_count({"hair": "golden", "eyes": "green"}) == 2
    assert detail_count(None, "an old woman") == 1
    assert detail_count(None, "a bony woman with sharp eyes and a thin mouth") == 3
    assert titled_variant("Magister Illyrio", None, "Illyrio Mopatis", None)
    assert titled_variant("Lady Arryn", None, "Lysa Arryn", {"sex": "woman"})
    assert not titled_variant("Lady Arryn", None, "Jon Arryn", {"sex": "man"})
    assert not titled_variant("Mr. Dursley", None, "Mrs. Dursley", None)
    assert not titled_variant("Dudley", None, "Dudley Dursley", None)  # plain variant: other rule


def test_merge_graph_merges_titled_duplicates_only_when_unambiguous():
    base = [
        {"id": "char_illyrio_mopatis", "name": "Illyrio Mopatis", "look": None},
        {"id": "char_lysa_arryn", "name": "Lysa Arryn", "look": {"type": "human", "sex": "woman"}},
        {"id": "char_jon_arryn", "name": "Jon Arryn", "look": {"type": "human", "sex": "man"}},
        {"id": "char_mrs_dursley", "name": "Mrs. Dursley", "look": None},
    ]
    new = [
        {"id": "char_magister_illyrio", "name": "Magister Illyrio", "look": None},
        {"id": "char_lady_arryn", "name": "Lady Arryn", "look": None},
        {"id": "char_mr_dursley", "name": "Mr. Dursley", "look": None},
    ]
    edges = [{"id": "e", "source": "char_magister_illyrio", "target": "char_lady_arryn",
              "relationship": "ally", "label": "", "evidence": ""}]
    nodes, merged_edges = merge_graph(base, [], new, edges)
    ids = {n["id"] for n in nodes}
    assert "char_magister_illyrio" not in ids and "char_lady_arryn" not in ids  # merged
    assert "char_mr_dursley" in ids  # Mr. never merges into Mrs.
    assert merged_edges[0]["source"] == "char_illyrio_mopatis"
    assert merged_edges[0]["target"] == "char_lysa_arryn"


@pytest.fixture()
def strict_env(env):
    """Default rules: 2 concrete details (or a main role) to be painted."""
    client, book_id, retrieval, chat, generator = env
    service = PortraitService(generator=generator, portraits_dir=get_settings().portraits_dir, min_details=2)
    client.app.dependency_overrides[get_portrait_service] = lambda: service
    return client, book_id, retrieval, chat, generator


def _look_char(name: str, role: str = "minor", **look) -> dict:
    return {"name": name, "role": role, "description": "", "look": look}


def test_too_little_description_waits_without_any_cost(strict_env):
    client, book_id, _, chat, generator = strict_env
    chat.characters = [
        _look_char("Dudley", sex="boy"),  # 0 details, minor -> waits
        _look_char("Mrs. Dursley", sex="woman", build="thin", hair="blonde"),  # 2 details -> painted
    ]
    _update(client, book_id)
    nodes = _nodes(client, book_id)
    assert nodes["Dudley"]["portrait_status"] == "waiting"
    assert nodes["Dudley"]["portrait_url"] is None
    assert nodes["Mrs. Dursley"]["portrait_status"] == "ready"
    assert generator.calls == 1
    assert client.get(f"/api/v1/books/{book_id}/characters/char_dudley/portrait").status_code == 404


def test_waiting_character_is_painted_once_described(strict_env):
    client, book_id, retrieval, chat, generator = strict_env
    chat.characters = [_look_char("Dudley", sex="boy")]
    _update(client, book_id)
    assert generator.calls == 0

    retrieval.read_more("Dudley was very large, with a pink face and thick blond hair.")
    chat.characters = [_look_char("Dudley", sex="boy", build="very large", hair="thick blond")]
    _update(client, book_id)
    assert generator.calls == 1
    assert _nodes(client, book_id)["Dudley"]["portrait_status"] == "ready"


def test_main_character_placeholder_is_upgraded_exactly_once(strict_env):
    client, book_id, retrieval, chat, generator = strict_env
    chat.characters = [_look_char("Harry", role="protagonist", sex="boy")]  # main, but no details
    _update(client, book_id)
    first_url = _nodes(client, book_id)["Harry"]["portrait_url"]
    assert generator.calls == 1  # main characters are painted anyway (as a placeholder)

    retrieval.read_more("Harry was small and skinny, with untidy black hair and green eyes.")
    chat.characters = [_look_char("Harry", role="protagonist", sex="boy", build="small and skinny",
                                  hair="untidy black", eyes="green")]
    _update(client, book_id)
    assert generator.calls == 2  # the one upgrade
    assert "untidy black hair" in generator.prompts[-1]
    assert _nodes(client, book_id)["Harry"]["portrait_url"] != first_url  # new version -> new URL

    retrieval.read_more("Harry wore Dudley's old clothes, far too big for him.")
    chat.characters = [_look_char("Harry", role="protagonist", sex="boy", build="small and skinny",
                                  hair="untidy black", eyes="green", clothing="baggy old clothes")]
    _update(client, book_id)
    assert generator.calls == 2  # never again


def test_portrait_from_a_real_description_is_never_upgraded(strict_env):
    client, book_id, retrieval, chat, generator = strict_env
    chat.characters = [_look_char("Harry", sex="boy", build="skinny", hair="black")]
    _update(client, book_id)
    retrieval.read_more("Harry had a thin face, knobbly knees and green eyes.")
    chat.characters = [_look_char("Harry", sex="boy", build="skinny", hair="black", eyes="green",
                                  distinctive="lightning scar")]
    _update(client, book_id)
    assert generator.calls == 1


def test_failed_upgrade_keeps_the_old_picture_and_retries(strict_env):
    client, book_id, retrieval, chat, generator = strict_env
    chat.characters = [_look_char("Harry", role="protagonist", sex="boy")]
    _update(client, book_id)
    old_bytes = client.get(_nodes(client, book_id)["Harry"]["portrait_url"]).content

    retrieval.read_more("Harry was small and skinny, with untidy black hair.")
    chat.characters = [_look_char("Harry", role="protagonist", sex="boy", build="small", hair="untidy black")]
    generator.fail_next = 1
    _update(client, book_id)
    node = _nodes(client, book_id)["Harry"]
    assert node["portrait_status"] == "ready"  # still showing the old one
    assert client.get(node["portrait_url"]).content == old_bytes

    retrieval.read_more("Harry ran down the stairs.")
    _update(client, book_id)
    assert client.get(_nodes(client, book_id)["Harry"]["portrait_url"]).content != old_bytes  # retried, upgraded


def test_legacy_placeholder_rows_are_recognised(strict_env):
    """Portraits made before the flag existed (e.g. "not described directly")
    are treated as placeholders and get their one upgrade."""
    client, book_id, retrieval, chat, generator = strict_env
    chat.characters = [_look_char("Harry", role="protagonist", sex="boy")]
    _update(client, book_id)

    from app.db import database
    from app.models.character_portrait import CharacterPortrait

    with database.SessionLocal() as db:
        row = db.query(CharacterPortrait).filter_by(book_id=book_id).one()
        row.placeholder, row.look_json, row.appearance = None, None, "not described directly"
        db.commit()

    retrieval.read_more("Harry was small and skinny, with untidy black hair.")
    chat.characters = [_look_char("Harry", role="protagonist", sex="boy", build="small", hair="untidy black")]
    _update(client, book_id)
    assert generator.calls == 2


def test_sync_reuses_portrait_for_a_titled_variant(strict_env):
    client, book_id, *_ = strict_env
    service = client.app.dependency_overrides[get_portrait_service]()
    from app.db import database

    with database.SessionLocal() as db:
        first = service.sync(db, book_id, [_node_dict("char_illyrio_mopatis", "Illyrio Mopatis")])
        assert len(first) == 1
        again = service.sync(db, book_id, [_node_dict("char_magister_illyrio", "Magister Illyrio")])
        assert again == []  # same person: no new portrait job
        from app.repositories import character_portrait_repository as prepo

        row = prepo.find_by_char_id(db, book_id, "char_magister_illyrio")
        assert row is not None and row.char_id == "char_illyrio_mopatis"


def _node_dict(char_id: str, name: str) -> dict:
    return {"id": char_id, "name": name, "role": "minor", "appearance": None,
            "look": {"type": "human", "sex": "man", "build": "fat", "facial_hair": "yellow beard"}}


# ---- one shared, genre-neutral title list ------------------------------------

from app.integrations.character_looks import ALL_TITLES  # noqa: E402
from app.integrations.portraits import describe_messages  # noqa: E402


@pytest.mark.parametrize(
    ("name", "sex"),
    [("Madame Maxime", "woman"), ("Mistress Quickly", "woman"), ("Señora Lopez", "woman"), ("Senora Lopez", "woman"),
     ("Monsieur Poirot", "man"), ("Professor Lupin", None), ("Inspector Lestrade", None), ("Doctor Watson", None)],
)
def test_titles_from_other_genres(name, sex):
    assert sex_from_name(name) == sex


def test_professional_titles_are_never_scrubbed_but_names_are():
    prompt = build_portrait_prompt(
        "a stern Professor in green robes, like Inspector Morse", names=["Professor McGonagall", "Inspector Morse"],
    )
    assert "Professor in green robes" in prompt
    assert "McGonagall" not in prompt and "Morse" not in prompt


def test_ai_prompts_use_neutral_title_examples():
    """No Game of Thrones-only titles as examples in what we send the text model."""
    extraction = cg._build_messages([_passage(CH1)])[1]["content"]
    describe = describe_messages("Harry", [_passage(CH1)])[1]["content"]
    for text in (extraction, describe):
        for got_only in ("Septa", "Ser/", "Ser,", "Maester", "Khal"):
            assert got_only not in text, got_only
        assert "Mr" in text and "Lady" in text


def test_flutter_initials_titles_match_the_shared_list():
    """frontend/lib/models/character_map_item.dart mirrors ALL_TITLES."""
    import re as _re

    dart = (Path(__file__).resolve().parents[2] / "frontend/lib/models/character_map_item.dart").read_text()
    block = dart.split("const titles = {", 1)[1].split("};", 1)[0]
    dart_titles = set(_re.findall(r"'([a-z]+)'", block))
    assert ALL_TITLES <= dart_titles
