"""Manual end-to-end check of the RAG pipeline (roadmap Steps 1-5).

    extract -> clean -> chunk -> embed -> Qdrant -> search

Run from `backend/` with the venv active. Examples:

    # offline: fake embedder + in-memory Qdrant (no Docker, no credentials)
    python scripts/try_rag.py "/path/to/book.pdf"

    # real Qdrant in Docker (docker compose --profile full up -d qdrant)
    python scripts/try_rag.py book.pdf --qdrant http://localhost:6333 --keep

    # real Cloudflare embeddings (reads backend/.env)
    python scripts/try_rag.py book.pdf --embedder cloudflare --qdrant http://localhost:6333 \\
        -q "Why was the cat looking at a map?"

The collection name includes the embedding model, so runs with different
embedders never collide (a collection is locked to one model).
"""
from __future__ import annotations

import argparse
import asyncio
import re
import sys
import time
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # so `app` imports work

from app.core.config import get_settings  # noqa: E402  (also loads backend/.env)
from app.rag.chunking import ChunkingConfig, chunk_document  # noqa: E402
from app.rag.cleaning import clean_document  # noqa: E402
from app.rag.embeddings import FakeEmbeddingProvider, build_embedding_provider  # noqa: E402
from app.rag.extraction import ExtractionError, extract_document  # noqa: E402
from app.rag.vector_store import QdrantVectorStore  # noqa: E402

BOOK_ID = "try-rag-book"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("book", help="path to a PDF or EPUB")
    p.add_argument("--embedder", choices=["fake", "cloudflare"], default="fake")
    p.add_argument("--qdrant", default="memory", help='"memory" (default) or a URL like http://localhost:6333')
    p.add_argument("-q", "--question", action="append", default=[], help="question to search for (repeatable)")
    p.add_argument("--max-page", type=int, default=None, help="spoiler boundary: only search up to this page/chapter")
    p.add_argument("--limit", type=int, default=3, help="results per question")
    p.add_argument("--keep", action="store_true", help="leave the vectors in Qdrant (to inspect the dashboard)")
    return p.parse_args()


def make_embedder(kind: str):
    settings = get_settings()
    if kind == "fake":
        return FakeEmbeddingProvider(settings.embedding_dimension)
    if not (settings.cloudflare_account_id and settings.cloudflare_api_token):
        sys.exit("Cloudflare credentials missing: set CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN in backend/.env")
    return build_embedding_provider(replace(settings, embedding_backend="cloudflare"))


async def main() -> int:
    args = parse_args()
    book = Path(args.book).expanduser()
    if not book.is_file():
        sys.exit(f"File not found: {book}")
    kind = book.suffix.lower().lstrip(".")
    settings = get_settings()

    print(f"== 1. Extract ({kind})")
    t = time.time()
    try:
        raw = extract_document(book, kind)
    except ExtractionError as exc:
        print(f"FAILED: {type(exc).__name__}: {exc}")
        return 1
    print(f"   {len(raw.sections)} sections | pages={raw.total_pages} | toc entries={len(raw.toc)} | {time.time() - t:.2f}s")

    print("== 2. Clean + chunk")
    t = time.time()
    chunks = chunk_document(
        BOOK_ID, clean_document(raw), ChunkingConfig(settings.chunk_target_tokens, settings.chunk_overlap_ratio)
    )
    sizes = [c.token_count for c in chunks]
    print(f"   {len(chunks)} chunks | tokens min/avg/max = {min(sizes)}/{sum(sizes) // len(sizes)}/{max(sizes)} | {time.time() - t:.2f}s")
    for c in chunks[:2]:
        print(f"   - {c.chunk_id} [{c.source_location}, chapter {c.chapter}] {c.text[:80]!r}")
    print(f"   overlap check: chunk 0 ends {chunks[0].text[-50:]!r}")
    print(f"                  chunk 1 starts {chunks[1].text[:50]!r}" if len(chunks) > 1 else "   (only one chunk)")

    print(f"== 3. Embed ({args.embedder})")
    embedder = make_embedder(args.embedder)
    print(f"   {type(embedder).__name__} | {embedder.model} | {embedder.dimension} dims")
    t = time.time()
    vectors = await embedder.embed([c.text for c in chunks])
    print(f"   {len(vectors)} vectors in {time.time() - t:.2f}s")

    print(f"== 4. Qdrant ({args.qdrant})")
    collection = "try_" + re.sub(r"[^a-z0-9]+", "_", embedder.model.lower()).strip("_")
    kwargs = dict(collection=collection, dimension=embedder.dimension, embedding_model=embedder.model)
    store = (
        QdrantVectorStore.in_memory(**kwargs)
        if args.qdrant == "memory"
        else QdrantVectorStore.from_url(args.qdrant, **kwargs)
    )
    store.ensure_collection()
    store.upsert(chunks, vectors)
    store.upsert(chunks, vectors)  # idempotent: must not double the count
    print(f"   collection={collection!r} | stored={store.count(BOOK_ID)} (expected {len(chunks)})")

    questions = args.question or [chunks[len(chunks) // 2].text[:120]]
    if not args.question:
        print("   (no -q given: using the start of a middle chunk as the query)")
    print("== 5. Search")
    status = 0
    for question in questions:
        q = (await embedder.embed([question]))[0]
        print(f"\n   Q: {question!r}" + (f"  [max position {args.max_page}]" if args.max_page else ""))
        hits = store.search(q, BOOK_ID, max_position=args.max_page, limit=args.limit)
        for h in hits:
            print(f"     {h.score:.3f}  {h.source_location:<14} {h.text[:90]!r}")
        if args.max_page is not None and any(h.position > args.max_page for h in hits):
            print("     !! SPOILER LEAK: a result is beyond the boundary")
            status = 1

    if args.keep:
        print(f"\nKept {store.count(BOOK_ID)} vectors in {collection!r}.")
    else:
        store.delete_book(BOOK_ID)
        print(f"\n== 6. Delete -> count now {store.count(BOOK_ID)}")
    print("DONE" if status == 0 else "DONE WITH PROBLEMS")
    return status


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
