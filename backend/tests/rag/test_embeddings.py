import asyncio
import logging

import httpx
import pytest

from app.core.config import Settings
from app.integrations.cloudflare import CloudflareClient, CloudflareNotConfiguredError
from app.rag.embeddings import (
    CloudflareEmbeddingProvider,
    EmbeddingError,
    FakeEmbeddingProvider,
    build_embedding_provider,
    embed_in_batches,
)

MODEL = "@cf/baai/bge-base-en-v1.5"


def cosine(a, b):
    return sum(x * y for x, y in zip(a, b))


def make_provider(handler, *, dimension=4, batch_size=2, concurrency=2):
    async def no_sleep(_):
        pass

    client = CloudflareClient("acct", "tok", transport=httpx.MockTransport(handler), sleep=no_sleep)
    return CloudflareEmbeddingProvider(client, MODEL, dimension, batch_size=batch_size, concurrency=concurrency)


def echo_handler(sizes=None, seen=None):
    """Each vector's first number is the text length, so order is checkable."""
    import json

    def handler(request):
        texts = json.loads(request.content)["text"]
        if sizes is not None:
            sizes.append(len(texts))
        if seen is not None:
            seen.extend(texts)
        return httpx.Response(200, json={"success": True, "result": {"data": [[float(len(t)), 0, 0, 1] for t in texts]}})

    return handler


# ---- embed_in_batches ----------------------------------------------------------


def test_batches_preserve_order_and_size():
    seen_batches = []

    async def embed_batch(batch):
        seen_batches.append(list(batch))
        return [[float(t)] for t in batch]

    texts = [str(i) for i in range(7)]
    result = asyncio.run(embed_in_batches(embed_batch, texts, batch_size=3, concurrency=2))
    assert result == [[float(i)] for i in range(7)]
    assert sorted(len(b) for b in seen_batches) == [1, 3, 3]


def test_batches_handle_empty_input_and_bad_arguments():
    async def embed_batch(batch):  # pragma: no cover - never called
        raise AssertionError

    assert asyncio.run(embed_in_batches(embed_batch, [], batch_size=4)) == []
    with pytest.raises(ValueError):
        asyncio.run(embed_in_batches(embed_batch, ["a"], batch_size=0))


def test_concurrency_is_bounded():
    state = {"running": 0, "peak": 0}

    async def embed_batch(batch):
        state["running"] += 1
        state["peak"] = max(state["peak"], state["running"])
        await asyncio.sleep(0.01)
        state["running"] -= 1
        return [[0.0] for _ in batch]

    asyncio.run(embed_in_batches(embed_batch, ["x"] * 10, batch_size=1, concurrency=3))
    assert state["peak"] == 3


# ---- Cloudflare provider -------------------------------------------------------


def test_cloudflare_provider_batches_and_keeps_order():
    sizes, seen = [], []
    provider = make_provider(echo_handler(sizes, seen))
    vectors = asyncio.run(provider.embed(["a", "bb", "ccc", "dddd", "eeeee"]))
    assert [v[0] for v in vectors] == [1.0, 2.0, 3.0, 4.0, 5.0]
    assert sorted(sizes) == [1, 2, 2]
    assert provider.model == MODEL and provider.dimension == 4


def test_cloudflare_provider_empty_input_makes_no_request():
    def handler(request):  # pragma: no cover - must not run
        raise AssertionError("no request expected")

    assert asyncio.run(make_provider(handler).embed([])) == []


def test_blank_text_is_replaced_with_a_space():
    seen = []
    provider = make_provider(echo_handler(seen=seen), batch_size=3)
    vectors = asyncio.run(provider.embed(["", "   ", "real"]))
    assert seen == [" ", " ", "real"]
    assert len(vectors) == 3


def test_wrong_vector_count_is_an_error():
    provider = make_provider(lambda r: httpx.Response(200, json={"success": True, "result": {"data": [[1, 2, 3, 4]]}}))
    with pytest.raises(EmbeddingError, match="Expected 2 vectors"):
        asyncio.run(provider.embed(["a", "b"]))


def test_wrong_dimension_is_an_error():
    provider = make_provider(lambda r: httpx.Response(200, json={"success": True, "result": {"data": [[1, 2]]}}))
    with pytest.raises(EmbeddingError, match="2-dim vector"):
        asyncio.run(provider.embed(["a"]))


def test_cloudflare_failure_becomes_embedding_error():
    provider = make_provider(lambda r: httpx.Response(401, json={"errors": [{"message": "bad token"}]}))
    with pytest.raises(EmbeddingError, match="bad token"):
        asyncio.run(provider.embed(["a"]))


# ---- fake provider -------------------------------------------------------------


def test_fake_provider_is_deterministic_normalised_and_sized():
    fake = FakeEmbeddingProvider(64)
    first, second = asyncio.run(fake.embed(["the red dragon", "the red dragon"]))
    assert first == second
    assert len(first) == 64 == fake.dimension
    assert abs(cosine(first, first) - 1.0) < 1e-9
    assert fake.model == "fake-hash-embedding"


def test_fake_provider_similarity_follows_shared_words():
    fake = FakeEmbeddingProvider(512)
    query, close, far = asyncio.run(fake.embed(["red dragon sleeps", "the red dragon sleeps here", "ocean tide moon"]))
    assert cosine(query, close) > cosine(query, far)


def test_fake_provider_handles_text_without_words():
    vector = asyncio.run(FakeEmbeddingProvider(8).embed(["!!!"]))[0]
    assert vector[0] == 1.0 and sum(vector[1:]) == 0.0


# ---- factory -------------------------------------------------------------------


def test_factory_fake_backend():
    provider = build_embedding_provider(Settings(embedding_backend="fake", embedding_dimension=32))
    assert isinstance(provider, FakeEmbeddingProvider) and provider.dimension == 32


def test_factory_auto_without_credentials_falls_back_with_warning(caplog):
    with caplog.at_level(logging.WARNING):
        provider = build_embedding_provider(Settings(embedding_backend="auto"))
    assert isinstance(provider, FakeEmbeddingProvider)
    assert "FAKE embedding provider" in caplog.text


def test_factory_cloudflare_backend_uses_settings():
    settings = Settings(
        embedding_backend="cloudflare", cloudflare_account_id="acct", cloudflare_api_token="tok",
        cloudflare_embedding_model="@cf/test/model", embedding_dimension=16,
        embedding_batch_size=5, embedding_concurrency=2,
    )
    provider = build_embedding_provider(settings)
    assert isinstance(provider, CloudflareEmbeddingProvider)
    assert (provider.model, provider.dimension) == ("@cf/test/model", 16)
    assert provider._batch_size == 5 and provider._concurrency == 2


def test_factory_auto_with_credentials_uses_cloudflare_and_given_client():
    settings = Settings(embedding_backend="auto", cloudflare_account_id="acct", cloudflare_api_token="tok")
    client = CloudflareClient("acct", "tok")
    provider = build_embedding_provider(settings, client=client)
    assert isinstance(provider, CloudflareEmbeddingProvider) and provider._client is client


def test_factory_cloudflare_without_credentials_fails_loudly():
    with pytest.raises(CloudflareNotConfiguredError):
        build_embedding_provider(Settings(embedding_backend="cloudflare"))


def test_factory_rejects_unknown_backend():
    with pytest.raises(ValueError, match="EMBEDDING_BACKEND"):
        build_embedding_provider(Settings(embedding_backend="magic"))
