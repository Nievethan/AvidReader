# Changes: RAG pipeline, Steps 1-5 (extraction through the Qdrant store)

Branch state: uncommitted on top of `main`. Owner: Umer. Roadmap reference: "RAG Pipeline Implementation Guide", section 8, Steps 1-5 (the PR2 deliverable).

## Summary

Adds the first half of the retrieval pipeline as standalone, fully tested library code:

```
PDF / EPUB -> extract -> clean -> chunk -> embed -> Qdrant
```

**Nothing is wired into the running app yet.** Upload still uses `mock_ingestion.py` and chat still uses `mock_ai.py`, so the UI behaves exactly as before. Wiring starts at roadmap Step 6 (background ingestion).

## How the pipeline works

| Stage | Module | What it does |
|---|---|---|
| Extract | `rag/extraction.py` | PDF: one `Section` per page, chapters from the PDF outline when present. EPUB: one `Section` per spine item (chapter = its number; nav page skipped). Detects scanned PDFs (`ScannedDocumentError`), encrypted or corrupt files (`ExtractionError`). |
| Clean | `rag/cleaning.py` | Removes running headers, footers and page numbers (PDF only), rejoins words hyphenated across lines, reflows hard-wrapped lines, normalises Unicode and control characters. Keeps section/page mapping 1:1. |
| Chunk | `rag/chunking.py` | Token-aware, paragraph-aligned chunks (default about 400 tokens, 12% sentence overlap). A chunk never crosses a chapter. Oversized paragraphs split on sentences, then words. Each chunk carries page range, chapter, `position` and `source_location`. |
| Embed | `rag/embeddings.py` | `EmbeddingProvider` protocol. Cloudflare Workers AI implementation (batched, bounded concurrency, dimension-checked) and a deterministic fake for tests and offline dev. `build_embedding_provider(settings)` picks one. |
| Store | `rag/vector_store.py` | One Qdrant collection for all books. `ensure_collection`, `upsert`, `search` (spoiler-bounded), `delete_book`, `count`. Pins the embedding model and dimension to the collection and refuses a mismatch. |
| HTTP client | `integrations/cloudflare.py` | Shared async Cloudflare client with retries (429/5xx/timeouts, `Retry-After`, exponential backoff). Used for embeddings; Gitae adds chat `generate` on top of `run`. |

### Spoiler boundary

Every chunk has a `position`: the **last page** it touches (PDF) or its **chapter number** (EPUB). `search(..., max_position=N)` filters in the Qdrant query itself (`position <= N`), so a chunk is only returned if all of its text is at or before the reader. This replaces the roadmap's `max_order_index`: `order_index` is now just the chunk's sequence number.

## Files

### New: application code (`backend/app/`)
- `rag/__init__.py`
- `rag/models.py` (`Section`, `ExtractedDocument`, `Chunk`, `TocEntry`)
- `rag/extraction.py`
- `rag/cleaning.py`
- `rag/chunking.py`
- `rag/embeddings.py`
- `rag/vector_store.py`
- `integrations/cloudflare.py`

### New: tests (`backend/tests/`)
- `rag/conftest.py` (generates a small PDF, a blank "scanned" PDF and an EPUB; nothing copyrighted is committed)
- `rag/test_models.py`, `test_extraction.py`, `test_cleaning.py`, `test_chunking.py`, `test_embeddings.py`, `test_vector_store.py`
- `test_cloudflare.py`
- `test_config.py`

### Modified
| File | Change |
|---|---|
| `backend/app/core/config.py` | New settings: `cloudflare_account_id`, `cloudflare_api_token`, `cloudflare_text_model`, `cloudflare_embedding_model` (default `@cf/baai/bge-base-en-v1.5`), `embedding_dimension` (768), `embedding_batch_size` (32), `embedding_concurrency` (4), `embedding_backend` (`auto`), `qdrant_collection`, `chunk_target_tokens` (400), `chunk_overlap_ratio` (0.12). Existing settings untouched. |
| `backend/.env.example` | Documents the new variables. Credentials stay blank. |
| `backend/requirements.txt` | Added `httpx` (now needed at runtime by the Cloudflare client), `pymupdf`, `EbookLib`, `beautifulsoup4`, `lxml`, `qdrant-client`. Also contains `pytest`. |
| `backend/requirements-dev.txt` | Added `pytest-cov`. |
| `backend/README.md` | Setup steps and folder tree now reference `requirements.txt` only. |
| `.gitignore` | Ignore `.coverage` and `htmlcov/`. |

### Not changed
All route handlers, services, models, schemas, `deps.py`, `main.py`, `docker-compose.yml`, the Dockerfile, the frontend, and the existing 28 tests.

## Configuration

Add to `backend/.env` (gitignored; never commit real values):

```
CLOUDFLARE_ACCOUNT_ID=<account id>
CLOUDFLARE_API_TOKEN=<api token>
EMBEDDING_BACKEND=cloudflare
```

- `EMBEDDING_BACKEND=auto` (default) uses Cloudflare when both credentials are set and otherwise falls back to the **fake** embedder with a logged warning. Use `cloudflare` in any real deployment so missing credentials fail loudly.
- Do not leave `CLOUDFLARE_EMBEDDING_MODEL=` or `EMBEDDING_DIMENSION=` present but empty. A blank value overrides the default. Omit the line to get the default.
- A Qdrant collection is pinned to one embedding model and dimension. Changing either means re-ingesting every book into a new collection.

## Testing

```bash
cd backend
source .venv/bin/activate          # Python 3.11 (matches the Dockerfile)
pip install -r requirements-dev.txt
pytest -q                          # 140 tests, no network or Docker needed
```

Coverage of everything added or changed (lines and branches):

```bash
pytest -q --cov=app.rag --cov=app.integrations.cloudflare --cov=app.core.config \
       --cov-branch --cov-report=term-missing
```

Result at the time of writing: **100%** on `app/rag/*`, `app/integrations/cloudflare.py` and `app/core/config.py`. Tests use in-memory Qdrant, `httpx.MockTransport` and the fake embedder, so CI needs no external services. Python 3.14 cannot build the pinned pydantic 2.9.2, so use 3.11.

### Also verified manually (not part of the automated suite)
- Harry Potter PDF, 250 pages: 312 chunks, max 397 tokens, overlap visible between chunks.
- Real Qdrant in Docker: upsert, spoiler-bounded search and delete by book worked; points visible in the dashboard.
- Live Cloudflare `@cf/baai/bge-base-en-v1.5`: 768-dim vectors, 312 chunks embedded in about 1.5 s; paraphrased questions landed on the correct pages.
- `docker compose build backend` succeeds with the new requirements.

## Behaviour notes and known limitations
- Chapters come only from the PDF outline or the EPUB spine. There is no heading detection, so a PDF without an outline is one group with `chapter=None`. Spoiler filtering still works because PDFs use page numbers.
- A paragraph that continues across a PDF page break is split into two pieces joined by a blank line.
- Hidden text on cover pages (for example leftover OCR) can end up in the first chunk.
- A genuine compound split at a line break (`well-\nknown`) is rejoined as `wellknown`; a hyphen before a capital is kept.
- Token counts are an estimate (1.3 x words), not a real tokenizer.
- Scanned PDFs are rejected; OCR is out of scope.
- No BGE query-instruction prefix is applied to questions. Evaluate in roadmap Step 9.
- Cloudflare's embedding request/response shape (`{"text": [...]}` in, `result.data` out) is verified live with one account; batch limits are not yet confirmed against the docs.

## Decisions to confirm with the team
1. `max_position` replaces `max_order_index` (see Spoiler boundary).
2. Embedding model `@cf/baai/bge-base-en-v1.5` at 768 dimensions (Gitae).
3. Whether `requirements-dev.txt` should be removed. The README now points at `requirements.txt`, but the dev file still exists, and `docs/TEAM_INTEGRATION.md` line 115 still references it (Abinav).
4. `docker-compose.yml` leaves `QDRANT_URL` blank for the backend; it is set when ingestion is wired up in Step 6.

## Next (roadmap)
- Step 6: background ingestion provider, `GET /books/{id}/ingestion`, delete hook, `/ready` Qdrant check.
- Step 7: `RetrievalProvider` and `list_chunks`, wired into `AIService`.
- Step 8: grounded answers with validated citations.
- Step 9: evaluation set (hit@k, faithfulness, latency, ingestion rate).
