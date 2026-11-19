"""Incremental character map: each Update only sends text not analyzed yet,
batched to fit the model's context window, merged into the saved map.
Regression for 413 "exceeded this model context window" on long books."""
from __future__ import annotations

import json

import pytest

from app.api.deps import get_character_graph_provider
from app.integrations.character_graph import (
    ERROR_MESSAGE,
    LLMCharacterGraphProvider,
    merge_graph,
    split_into_batches,
)
from app.integrations.interfaces import RetrievedPassage
from tests.conftest import make_minimal_pdf_bytes, upload


def _p(i: int, text: str) -> RetrievedPassage:
    return RetrievedPassage(
        book_id="b", chunk_id=f"c{i}", text=text, source_location=f"page {i + 1}", order_index=i
    )


class _Retrieval:
    """`passages` = everything up to the reader's current position."""

    def __init__(self, passages):
        self.passages = passages

    async def list_chunks(self, book_id, boundary, last_n=None):
        return list(self.passages)

    async def retrieve(self, *args, **kwargs):
        raise NotImplementedError


class _Model:
    """Answers each prompt with the characters (from `cast`) whose name
    appears in that prompt's excerpts; records every prompt."""

    status = "ok"
    name = "stub"

    def __init__(self, cast: dict[str, str], relationships: list[dict] | None = None):
        self.cast = cast
        self.relationships = relationships or []
        self.prompts: list[str] = []
        self.fail_on_call: set[int] = set()

    async def complete(self, messages, *, max_tokens):
        prompt = messages[-1]["content"]
        self.prompts.append(prompt)
        if len(self.prompts) in self.fail_on_call:
            raise RuntimeError("Cloudflare API error 413: context window exceeded")
        excerpts = prompt.split("CHARACTERS ALREADY KNOWN")[0]
        chars = [{"name": n, "role": r, "description": f"{n} appears"} for n, r in self.cast.items() if n in excerpts]
        rels = [r for r in self.relationships if r["evidence"] in excerpts]
        return json.dumps({"characters": chars, "relationships": rels})


@pytest.fixture()
def setup(client):
    def _make(passages, model, **kwargs):
        retrieval = _Retrieval(passages)
        provider = LLMCharacterGraphProvider(retrieval_provider=retrieval, chat_model=model, **kwargs)
        client.app.dependency_overrides[get_character_graph_provider] = lambda: provider
        return retrieval

    book = upload(client, make_minimal_pdf_bytes())
    yield client, book["id"], _make
    client.app.dependency_overrides.pop(get_character_graph_provider, None)


def _update(client, book_id) -> dict:
    res = client.post(f"/api/v1/books/{book_id}/relationships/generate")
    assert res.status_code == 200, res.text
    return res.json()


def _names(body) -> set[str]:
    return {n["name"] for n in body["nodes"]}


def test_second_update_only_sends_new_pages_and_merges(setup):
    client, book_id, make = setup
    model = _Model(
        {"Alice": "protagonist", "Bob": "ally", "Carol": "rival"},
        [{"source": "Carol", "target": "Alice", "relationship": "rival", "label": "x",
          "evidence": "Carol glared at Alice."}],
    )
    retrieval = make([_p(0, "Alice met Bob at the gate."), _p(1, "Bob laughed.")], model)

    first = _update(client, book_id)
    assert _names(first) == {"Alice", "Bob"}
    assert len(model.prompts) == 1

    # Reader moves on two pages.
    retrieval.passages += [_p(2, "Carol arrived."), _p(3, "Carol glared at Alice.")]
    second = _update(client, book_id)

    assert len(model.prompts) == 2
    new_prompt = model.prompts[1]
    assert "Alice met Bob at the gate." not in new_prompt  # old pages not re-sent
    assert "Carol arrived." in new_prompt
    assert "CHARACTERS ALREADY KNOWN FROM EARLIER PAGES: Alice, Bob" in new_prompt
    assert _names(second) == {"Alice", "Bob", "Carol"}  # earlier characters kept
    # A relationship from the new pages can point at a character from earlier pages.
    assert [(e["source"], e["target"]) for e in second["edges"]] == [("char_carol", "char_alice")]

    # GET returns the merged map without another model call.
    cached = client.get(f"/api/v1/books/{book_id}/relationships").json()
    assert _names(cached) == {"Alice", "Bob", "Carol"}
    assert len(model.prompts) == 2


def test_update_with_no_new_pages_makes_no_model_call(setup):
    client, book_id, make = setup
    model = _Model({"Alice": "protagonist"})
    make([_p(0, "Alice smiled.")], model)
    _update(client, book_id)
    body = _update(client, book_id)
    assert len(model.prompts) == 1
    assert _names(body) == {"Alice"}


def test_long_read_is_split_into_batches_that_fit(setup):
    client, book_id, make = setup
    model = _Model({"Alice": "protagonist", "Zed": "minor"})
    passages = [_p(i, ("Alice walked. " if i == 0 else "") + ("Zed waved. " if i == 39 else "") + "x" * 1000)
                for i in range(40)]
    make(passages, model, batch_chars=10_000, max_batches=10)

    body = _update(client, book_id)
    assert len(model.prompts) == 5  # ~40k chars / 10k per batch
    for prompt in model.prompts:
        assert prompt.count("x" * 1000) <= 10  # each batch within budget
    assert _names(body) == {"Alice", "Zed"}  # first and last page both covered
    assert body["message"] is None


def test_batch_cap_saves_progress_and_next_update_continues(setup):
    client, book_id, make = setup
    model = _Model({"Alice": "protagonist", "Zed": "minor"})
    passages = [_p(i, ("Alice walked. " if i == 0 else "") + ("Zed waved. " if i == 39 else "") + "x" * 1000)
                for i in range(40)]
    make(passages, model, batch_chars=10_000, max_batches=2)

    first = _update(client, book_id)
    assert len(model.prompts) == 2
    assert first["status"] == "ready"
    assert _names(first) == {"Alice"}
    assert "Tap Update again to continue" in first["message"]
    assert first["boundary_label"] == "page 19"  # where it got to, not the reader's position

    second = _update(client, book_id)
    assert len(model.prompts) == 4
    assert "page 1)" not in model.prompts[2]  # resumes after page 19
    third = _update(client, book_id)
    assert len(model.prompts) == 5
    assert _names(third) == {"Alice", "Zed"}
    assert third["message"] is None
    assert second["status"] == "ready"


def test_ai_error_midway_keeps_progress_and_retries_from_there(setup):
    client, book_id, make = setup
    model = _Model({"Alice": "protagonist", "Zed": "minor"})
    passages = [_p(i, ("Alice walked. " if i == 0 else "") + ("Zed waved. " if i == 29 else "") + "x" * 1000)
                for i in range(30)]
    make(passages, model, batch_chars=10_000, max_batches=10)
    model.fail_on_call = {2}

    first = _update(client, book_id)
    assert first["status"] == "ready"
    assert _names(first) == {"Alice"}
    assert "returned an error" in first["message"]

    second = _update(client, book_id)
    assert _names(second) == {"Alice", "Zed"}
    assert "Alice walked." not in "".join(model.prompts[2:])  # batch 1 not redone


def test_first_failure_with_no_saved_map_shows_real_error_not_placeholder(setup):
    client, book_id, make = setup
    model = _Model({"Alice": "protagonist"})
    model.fail_on_call = {1}
    make([_p(0, "Alice smiled.")], model)
    body = _update(client, book_id)
    assert body["status"] == "not_available"
    assert body["message"] == ERROR_MESSAGE
    assert "Gitae" not in body["message"]


def test_failure_with_saved_map_keeps_showing_it(setup):
    client, book_id, make = setup
    model = _Model({"Alice": "protagonist", "Bob": "ally"})
    retrieval = make([_p(0, "Alice smiled.")], model)
    _update(client, book_id)

    retrieval.passages.append(_p(1, "Bob arrived."))
    model.fail_on_call = {2}
    body = _update(client, book_id)
    assert body["status"] == "ready"
    assert _names(body) == {"Alice"}
    assert body["message"] == ERROR_MESSAGE


def test_moving_backwards_rebuilds_up_to_the_new_position(setup):
    """Spoiler safety: a map built through page 4 must not survive the
    reader going back to page 1."""
    client, book_id, make = setup
    model = _Model({"Alice": "protagonist", "Carol": "rival"})
    retrieval = make([_p(0, "Alice smiled."), _p(1, "x"), _p(2, "x"), _p(3, "Carol arrived.")], model)
    assert _names(_update(client, book_id)) == {"Alice", "Carol"}

    retrieval.passages = retrieval.passages[:1]
    body = _update(client, book_id)
    assert _names(body) == {"Alice"}
    assert "Alice smiled." in model.prompts[-1]


def test_map_saved_before_incremental_extraction_is_rebuilt_once(setup):
    client, book_id, make = setup
    model = _Model({"Alice": "protagonist"})
    make([_p(0, "Alice smiled.")], model)
    _update(client, book_id)

    from app.db import database
    from app.models.character_graph import CharacterGraphCache

    with database.SessionLocal() as db:
        db.get(CharacterGraphCache, book_id).processed_through_order = None  # legacy row
        db.commit()
    _update(client, book_id)
    assert len(model.prompts) == 2  # full rebuild
    _update(client, book_id)
    assert len(model.prompts) == 2  # then incremental again


# ---- unit tests ------------------------------------------------------------


def test_merge_graph_merges_unambiguous_name_variant_and_remaps_edges():
    base = [{"id": "char_dudley", "name": "Dudley", "role": "unknown", "description": "a boy",
             "first_seen_chunk_id": "c1"}]
    new = [{"id": "char_dudley_dursley", "name": "Dudley Dursley", "role": "rival", "description": "a big boy",
            "first_seen_chunk_id": "c9"},
           {"id": "char_harry", "name": "Harry", "role": "protagonist", "description": "", "first_seen_chunk_id": "c9"}]
    edges = [{"id": "e", "source": "char_dudley_dursley", "target": "char_harry", "relationship": "rival",
              "label": "", "evidence": "q"}]
    nodes, out_edges = merge_graph(base, [], new, edges)
    by_id = {n["id"]: n for n in nodes}
    assert set(by_id) == {"char_dudley", "char_harry"}
    assert by_id["char_dudley"]["name"] == "Dudley Dursley"
    assert by_id["char_dudley"]["role"] == "rival"
    assert by_id["char_dudley"]["first_seen_chunk_id"] == "c1"
    assert out_edges[0]["source"] == "char_dudley"


def test_merge_graph_never_merges_mr_and_mrs_or_ambiguous_names():
    base = [{"id": "char_mr_dursley", "name": "Mr. Dursley"}, {"id": "char_mrs_dursley", "name": "Mrs. Dursley"}]
    nodes, _ = merge_graph(base, [], [{"id": "char_dursley", "name": "Dursley"}], [])
    assert {n["id"] for n in nodes} == {"char_mr_dursley", "char_mrs_dursley", "char_dursley"}


def test_split_into_batches_respects_budget_order_and_truncates_oversized():
    passages = [_p(i, "x" * 400) for i in range(10)] + [_p(10, "y" * 5000)]
    batches = split_into_batches(passages, 1000)
    assert all(sum(len(p.text) for p in b) <= 1000 for b in batches)
    flat = [p.order_index for b in batches for p in b]
    assert flat == list(range(11))
    assert len(batches[-1][0].text) == 1000


# ---- malformed model JSON (regression: "Expecting ',' delimiter" at page ~78) ----

from app.integrations.character_graph import _parse_json  # noqa: E402


def test_parse_json_repairs_unescaped_dialogue_quotes_and_trailing_commas():
    broken = (
        '{"characters":[{"name":"Ned","role":"lord",},],'
        '"relationships":[{"source":"Ned","target":"Jon","relationship":"father",'
        '"evidence":"He said "Winter is coming" and left"}]}'
    )
    obj = _parse_json(broken)
    assert obj["characters"][0]["name"] == "Ned"
    assert obj["relationships"][0]["evidence"] == 'He said "Winter is coming" and left'


class _FlakyJSONModel(_Model):
    """Returns unparseable text for any prompt containing a marker passage."""

    def __init__(self, cast, bad_marker: str):
        super().__init__(cast)
        self.bad_marker = bad_marker

    async def complete(self, messages, *, max_tokens):
        reply = await super().complete(messages, max_tokens=max_tokens)
        excerpts = messages[-1]["content"].split("CHARACTERS ALREADY KNOWN")[0]
        return "{this is : not json" if self.bad_marker in excerpts else reply



def test_unparseable_reply_is_split_and_retried(setup):
    client, book_id, make = setup
    passages = [_p(i, t) for i, t in enumerate(["Alice smiled.", "x", "BAD", "Zed waved."])]
    model = _FlakyJSONModel({"Alice": "protagonist", "Zed": "minor"}, bad_marker="BAD")
    make(passages, model)

    body = _update(client, book_id)
    assert body["status"] == "ready"
    assert _names(body) == {"Alice", "Zed"}  # halves without the bad passage still extracted
    assert "skipped" in body["message"] and "page 3" in body["message"]


def test_unparseable_section_never_blocks_progress(setup):
    client, book_id, make = setup
    model = _FlakyJSONModel({"Alice": "protagonist"}, bad_marker="BAD")
    retrieval = make([_p(0, "Alice smiled.")], model)
    _update(client, book_id)

    retrieval.passages.append(_p(1, "BAD"))
    body = _update(client, book_id)
    assert body["status"] == "ready" and "skipped" in body["message"]
    calls = len(model.prompts)
    _update(client, book_id)  # nothing new: the bad page isn't retried forever
    assert len(model.prompts) == calls
