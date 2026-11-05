import asyncio

import pytest
from qdrant_client import QdrantClient, models

from app.rag import vector_store as vs
from app.rag.embeddings import FakeEmbeddingProvider
from app.rag.models import Chunk
from app.rag.vector_store import (
    QdrantVectorStore,
    VectorStoreConfigError,
    VectorStoreError,
    point_id,
)

DIM = 64
MODEL = "fake-hash-embedding"
emb = FakeEmbeddingProvider(DIM)


def make_chunks(book_id, texts, *, first_page=1):
    return [
        Chunk(
            chunk_id=f"{book_id}:{i}", book_id=book_id, order_index=i, text=text,
            page_start=first_page + i, page_end=first_page + i, chapter=None, chapter_title=None,
            token_count=len(text.split()),
        )
        for i, text in enumerate(texts)
    ]


def embed(texts):
    return asyncio.run(emb.embed(texts))


@pytest.fixture()
def store():
    s = QdrantVectorStore.in_memory(collection="t", dimension=DIM, embedding_model=MODEL)
    s.ensure_collection()
    return s


def load(store, book_id, texts, **kw):
    chunks = make_chunks(book_id, texts, **kw)
    store.upsert(chunks, embed(texts))
    return chunks


TEXTS = [
    "red dragon guards the mountain pass",
    "baker bread village winter altar",
    "sea captain sails the ship at dawn",
    "storm breaks the mast and the letter is lost",
]


def test_point_id_is_stable_uuid():
    assert point_id("b:1") == point_id("b:1") != point_id("b:2")
    assert len(point_id("b:1")) == 36


def test_factories(monkeypatch):
    memory = QdrantVectorStore.in_memory(collection="c", dimension=8, embedding_model="m")
    assert (memory.collection, memory.dimension, memory.embedding_model) == ("c", 8, "m")

    captured = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(vs, "QdrantClient", FakeClient)
    QdrantVectorStore.from_url("http://qdrant:6333", collection="c", dimension=8, embedding_model="m")
    assert captured == {"url": "http://qdrant:6333", "timeout": 30}


def test_ensure_collection_creates_once_and_is_idempotent(store):
    store.ensure_collection()
    info = store._client.get_collection("t")
    assert info.config.params.vectors.size == DIM
    assert info.config.metadata == {"embedding_model": MODEL, "dimension": DIM}


def test_dimension_mismatch_is_refused(store):
    other = QdrantVectorStore(store._client, collection="t", dimension=DIM * 2, embedding_model=MODEL)
    with pytest.raises(VectorStoreConfigError, match="vector size"):
        other.ensure_collection()


def test_model_mismatch_is_refused(store):
    other = QdrantVectorStore(store._client, collection="t", dimension=DIM, embedding_model="another-model")
    with pytest.raises(VectorStoreConfigError, match="another-model"):
        other.ensure_collection()
    assert issubclass(VectorStoreConfigError, VectorStoreError)


def test_collection_without_model_metadata_is_accepted():
    client = QdrantClient(":memory:")
    client.create_collection("t", vectors_config=models.VectorParams(size=DIM, distance=models.Distance.COSINE))
    QdrantVectorStore(client, collection="t", dimension=DIM, embedding_model=MODEL).ensure_collection()


def test_named_vector_collections_skip_the_size_check():
    client = QdrantClient(":memory:")
    client.create_collection(
        "t", vectors_config={"dense": models.VectorParams(size=3, distance=models.Distance.COSINE)}
    )
    QdrantVectorStore(client, collection="t", dimension=DIM, embedding_model=MODEL).ensure_collection()


def test_upsert_stores_payload(store):
    load(store, "book", TEXTS)
    assert store.count("book") == 4
    hit = store.search(embed([TEXTS[2]])[0], "book", limit=1)[0]
    assert hit.chunk_id == "book:2" and hit.book_id == "book"
    assert (hit.order_index, hit.position, hit.page_start, hit.page_end) == (2, 3, 3, 3)
    assert hit.source_location == "page 3" and hit.text == TEXTS[2]
    assert hit.chapter is None and hit.chapter_title is None
    assert hit.score > 0.99


def test_reupsert_overwrites_instead_of_duplicating(store):
    load(store, "book", TEXTS)
    load(store, "book", TEXTS)
    assert store.count("book") == 4


def test_upsert_validates_inputs(store):
    chunks = make_chunks("book", TEXTS[:2])
    with pytest.raises(VectorStoreError, match="2 chunks but 1 vectors"):
        store.upsert(chunks, embed(TEXTS[:1]))
    with pytest.raises(VectorStoreError, match="3 dims"):
        store.upsert(chunks, [[0.1, 0.2, 0.3], [0.1, 0.2, 0.3]])


def test_upsert_batches_large_books(store):
    texts = [f"unique token{i} filler" for i in range(130)]  # > 2 batches of 64
    load(store, "big", texts)
    assert store.count("big") == 130


def test_search_ranks_by_similarity_and_limits(store):
    load(store, "book", TEXTS)
    results = store.search(embed(["sea captain ship"])[0], "book", limit=2)
    assert len(results) == 2
    assert results[0].chunk_id == "book:2"
    assert results[0].score >= results[1].score


def test_search_respects_spoiler_boundary(store):
    load(store, "book", TEXTS)  # positions 1..4
    query = embed(["sea captain ship storm"])[0]
    bounded = store.search(query, "book", max_position=2, limit=10)
    assert bounded and all(h.position <= 2 for h in bounded)
    assert store.search(query, "book", max_position=0) == []
    assert len(store.search(query, "book", max_position=None, limit=10)) == 4


def test_search_is_scoped_to_one_book(store):
    load(store, "one", TEXTS)
    load(store, "two", ["dragon in another book entirely"])
    results = store.search(embed(["dragon"])[0], "two", limit=10)
    assert {h.book_id for h in results} == {"two"}


def test_search_min_score_filters_weak_matches(store):
    load(store, "book", TEXTS)
    assert store.search(embed(["zebra quantum"])[0], "book", min_score=0.9) == []


def test_search_rejects_wrong_dimension(store):
    with pytest.raises(VectorStoreError, match="3 dims"):
        store.search([0.1, 0.2, 0.3], "book")


def test_delete_book_removes_only_that_book(store):
    load(store, "one", TEXTS)
    load(store, "two", TEXTS[:2])
    store.delete_book("one")
    assert store.count("one") == 0 and store.count("two") == 2
    store.delete_book("never-existed")  # no error


def test_epub_style_chunks_keep_chapter_metadata(store):
    chunk = Chunk(
        chunk_id="e:0", book_id="e", order_index=0, text="lighthouse keeper counts ships",
        page_start=None, page_end=None, chapter=2, chapter_title="Two", token_count=4,
    )
    store.upsert([chunk], embed([chunk.text]))
    hit = store.search(embed([chunk.text])[0], "e", max_position=2)[0]
    assert (hit.chapter, hit.chapter_title, hit.page_start, hit.source_location) == (2, "Two", None, "chapter 2")
    assert store.search(embed([chunk.text])[0], "e", max_position=1) == []
