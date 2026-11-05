"""Step 4: embedding providers.

takes the text chunks from your textbook and 
converts them into lists of numbers called vectors (embeddings).

`EmbeddingProvider` is the seam: Cloudflare Workers AI in production, a
deterministic hash-based fake for tests and offline dev. A Qdrant collection
is pinned to one (model, dimension); queries must use the same provider as
the documents.

BGE retrieval models work best when *queries* (not documents) carry an
instruction prefix; not applied yet -- evaluate in Step 9.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import re
from collections.abc import Awaitable, Callable
from typing import Protocol

from app.core.config import Settings
from app.integrations.cloudflare import CloudflareClient, CloudflareError

logger = logging.getLogger(__name__)


class EmbeddingError(Exception):
    pass


# It connects to Cloudflare Workers AI and asks an embedding model to convert textbook chunks into numerical vectors.
class EmbeddingProvider(Protocol):
    model: str
    dimension: int

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """One vector per input text, same order, each of length `dimension`."""
        ...

# The chunk texts are split into batches of 32, so about 13 batches for 400 chunks. Up to 4 batches are sent to Cloudflare at once.
async def embed_in_batches(
    embed_batch: Callable[[list[str]], Awaitable[list[list[float]]]],
    texts: list[str],
    *,
    batch_size: int,
    concurrency: int = 4,
) -> list[list[float]]:
    """Split `texts` into batches, run up to `concurrency` at once, and
    return vectors in input order."""
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")
    batches = [texts[i : i + batch_size] for i in range(0, len(texts), batch_size)]
    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def run(batch: list[str]) -> list[list[float]]:
        async with semaphore:
            return await embed_batch(batch)

    results = await asyncio.gather(*(run(b) for b in batches))
    return [vector for batch_vectors in results for vector in batch_vectors]

# Send text to Cloudflare Workers AI to get embeddings in batches, with concurrency control.
class CloudflareEmbeddingProvider:
    def __init__(
        self,
        client: CloudflareClient,
        model: str,
        dimension: int,
        *,
        batch_size: int = 32,
        concurrency: int = 4,
    ) -> None:
        self._client = client
        self.model = model
        self.dimension = dimension
        self._batch_size = batch_size
        self._concurrency = concurrency

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        # Each batch is validated in _embed_batch, so the combined result
        # always has exactly one vector per input text.
        return await embed_in_batches(
            self._embed_batch, texts, batch_size=self._batch_size, concurrency=self._concurrency
        )

    async def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        # The API rejects empty strings; a blank stand-in keeps ordering intact.
        safe = [t if t.strip() else " " for t in batch]
        try:
            vectors = await self._client.embed(self.model, safe)
        except CloudflareError as exc:
            raise EmbeddingError(str(exc)) from exc
        if len(vectors) != len(batch):
            raise EmbeddingError(f"Expected {len(batch)} vectors in batch, got {len(vectors)}.")
        for vector in vectors:
            if len(vector) != self.dimension:
                raise EmbeddingError(
                    f"Model {self.model} returned a {len(vector)}-dim vector; "
                    f"EMBEDDING_DIMENSION is {self.dimension}."
                )
        return vectors

# A deterministic bag-of-words hashing embedder. Texts sharing words get a higher cosine similarity, so retrieval tests behave sensibly with no network, credentials or model download. Not for production.
class FakeEmbeddingProvider:
    """Deterministic bag-of-words hashing embedder. Texts sharing words get
    a higher cosine similarity, so retrieval tests behave sensibly with no
    network, credentials or model download. Not for production."""

    def __init__(self, dimension: int = 256, model: str = "fake-hash-embedding") -> None:
        self.model = model
        self.dimension = dimension

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for token in re.findall(r"\w+", text.lower()):
            digest = hashlib.md5(token.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dimension
            vector[bucket] += 1.0 if digest[4] % 2 == 0 else -1.0
        norm = math.sqrt(sum(v * v for v in vector))
        if norm == 0:
            vector[0] = 1.0
            return vector
        return [v / norm for v in vector]


def build_embedding_provider(settings: Settings, client: CloudflareClient | None = None) -> EmbeddingProvider:
    backend = settings.embedding_backend
    has_credentials = bool(settings.cloudflare_account_id and settings.cloudflare_api_token)
    if backend == "fake" or (backend == "auto" and not has_credentials):
        if backend == "auto":
            logger.warning("Cloudflare credentials not set; using the FAKE embedding provider (dev only).")
        return FakeEmbeddingProvider(dimension=settings.embedding_dimension)
    if backend not in ("auto", "cloudflare"):
        raise ValueError(f"Unknown EMBEDDING_BACKEND: {backend!r}")
    client = client or CloudflareClient(settings.cloudflare_account_id, settings.cloudflare_api_token)
    return CloudflareEmbeddingProvider(
        client,
        settings.cloudflare_embedding_model,
        settings.embedding_dimension,
        batch_size=settings.embedding_batch_size,
        concurrency=settings.embedding_concurrency,
    )
