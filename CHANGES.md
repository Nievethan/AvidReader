# Changes: RAG pipeline, Steps 1-9

Owner: Umer. Roadmap reference: "RAG Pipeline Implementation Guide", section 8.
Branch: `AI-Model-Pipeline`. Steps 1-5 are committed; Steps 6-9 are uncommitted.

| Part | Status |
|---|---|
| Steps 1-5: extraction, cleaning, chunking, embeddings, Qdrant store | Committed (PR2 deliverable). Details in the second half of this file. |
| Steps 6-9: ingestion, retrieval, grounded answers, evaluation | Implemented, uncommitted. Details below. |

---

# Steps 6-9: the pipeline wired into the app

## Summary

The pipeline is now live in the backend. Uploading a book indexes it, the reader gets the real text, and chat answers come from the book with page citations, limited to what the reader has read.

```
upload ─► 201 {processing_status: "processing"}
  └─ background job: extract ─► clean ─► chunk ─► embed ─► Qdrant (+ saved page text)
        status: processing ─► ready | unsupported (scanned PDF) | failed

question ─► spoiler limit ─► retrieve top 8 chunks (position <= limit) ─► prompt ─► chat model
        ─► citation / quote / copy checks ─► answer + citations + spoiler_scope
```

Models (Cloudflare Workers AI):
- **Embeddings:** `@cf/baai/bge-base-en-v1.5` (768 dimensions), unchanged from Step 4.
- **Chat:** default `@cf/qwen/qwen3-30b-a3b-fp8` (the only benchmarked model under the 2.5 s p95 target, see Step 9); `@cf/meta/llama-3.3-70b-instruct-fp8-fast` is supported as a slightly more accurate but slower alternative. Chosen with `CLOUDFLARE_TEXT_MODEL`.

## Step 6: ingestion wired into upload and delete

- **Background ingestion:** `POST /books` stores the file and returns at once with `processing`. A FastAPI `BackgroundTasks` job runs the full pipeline on the whole book and records `ready` / `unsupported` / `failed`, `total_pages` and `chunk_count`. The job uses its own database session.
- **Status route:** `GET /api/v1/books/{id}/ingestion` returns `{status, message, total_pages, chunk_count, attempts, updated_at}`.
- **Reader text:** `GET /api/v1/books/{id}/content?page=N` (PDF) or `?chapter=N` (EPUB) returns the real cleaned text, saved once at ingestion. Out-of-range pages return 404.
- **Delete:** also removes the book's vectors and saved text. If Qdrant is down, the book is still deleted and a warning is logged.
- **Restart recovery:** books left in `processing` by a server restart are re-indexed once at startup; a second interruption marks them `failed`.
- **Vector store modes:** `QDRANT_URL` set uses the Qdrant server; blank uses embedded Qdrant saved in `backend/data/qdrant/` (no Docker needed).
- **Database:** `books` gained `chunk_count` and `ingestion_attempts`. A startup check adds them to existing databases, so nobody has to delete their local `avidreader.db`.
- **Readiness:** `/ready` now checks Qdrant for real (`vector_store: {mode, status}`).
- **Docker:** Qdrant always starts with `docker compose up`; the backend uses `QDRANT_URL=http://qdrant:6333`. Neo4j stays under `--profile full`.

## Step 7: retrieval wired into chat

- **Retrieval provider:** embeds the question, searches Qdrant for the book's closest chunks (top 8, minimum score 0.5) with the spoiler limit applied inside the query.
- **Spoiler limit:** page for PDF, chapter for EPUB. Taken from the chat request's `reading_position`, else the saved reading progress, else no limit. `spoiler_scope` reports which, e.g. "Limited to page 60 (your current position)."
- **`list_chunks()`:** every chunk up to the limit in reading order, or only the last n. Used by `story_continues` and available for Gitae's character map / environment features.
- **`format_passages()`:** the numbered `[S1] (page 12)` block that prompts consume.
- **Context per interaction:** `question` / `what_if` search with the question; `explain` searches with the selected passage; `story_continues` uses the last 3 chunks before the reader.
- **Book not ready:** chat answers that the book is still processing / failed / unsupported instead of searching.

## Step 8: grounded answers

- **`generate()`** added to the shared async Cloudflare client (chat completions, both Cloudflare response shapes, `<think>` blocks removed, per-call timeout and retry limit). Gitae can reuse it.
- **Prompts:** rules (answer only from the excerpts, cite `[S#]`, reply `NOT_FOUND` if not covered, no spoilers, short quotes only, ignore instructions inside book text) plus variants for interaction type, mode and explanation level. Recent conversation is sent as chat history.
- **One provider for all four types:** `question`, `explain` (answer_type `grounded`), `what_if`, `story_continues` (answer_type `hypothetical`). `story_continues` writes a short original continuation and must not reveal later events or copy the book.
- **Checks on every answer:** unknown `[S#]` markers removed; quotations not found in the excerpts lose their quote marks; copied sentences removed from continuations; a factual answer with no valid citation becomes the refusal "I couldn't find this in the part of the book you've read so far."
- **No evidence:** if nothing relevant is found, the refusal is returned without calling the model.
- **Failures:** a model timeout or error returns `answer_type: "unavailable"`, not a crash.
- **Citations:** typed `{marker, chunk_id, page_start, page_end, page, chapter, source_location, snippet, score}`. `page` keeps the current frontend's "p. N" chip working.
- **Offline fallback:** without credentials (or with `ANSWER_BACKEND=fake`), a labelled extractive answerer is used, so the app and tests work offline.

## Step 9: evaluation and model benchmark

- **`backend/scripts/eval_rag.py`:** runs the real app in-process (temporary database, in-memory Qdrant, your `.env` models): upload, ingestion, reader text, retrieval hit@k, then every question through `/ai/chat`. Scores answerable, unanswerable, spoiler and hypothetical questions, citation validity and latency. `--models a,b` benchmarks chat models on the same questions; `--ids` runs a subset; `--report` saves JSON.
- **Question sets** (questions, keywords and gold pages only; no book text):
  - `tests/eval/harry_potter_1_first99.json` (default): 20 questions for `SplitPDF.pdf`, pages 2-100 of the book. About 40% of the full book's indexing cost.
  - `tests/eval/harry_potter_1.json`: 30 questions for the full 250-page PDF.
- **Tuning applied:** `RETRIEVAL_TOP_K` raised from 5 to 8. With 5, answers in neighbouring chunks were missed (q05, q08, q11); with 8 they were found.

### Results (live Cloudflare, Harry Potter book 1)

Full 250-page book, Llama 3.3, top-k 8:

| Metric | Result | Target |
|---|---|---|
| Ingestion speed | 250 pages, 312 chunks in ~2.2 s (~6,800 pages/min) | ≥ 50 pages/min (ER-05) |
| Retrieval hit@8 | 20/21 (95.2%) | ≥ 95% (ER-04) |
| Answerable questions | 18/21 (2 of the 3 misses had the right answer but cited non-gold pages) | |
| Unanswerable (refusals) | 4/4 | |
| Spoiler tests | 3/3 | |
| Hypothetical | 2/2 labelled | |
| Citation validity | 20/20 | |
| Latency | p50 4.7 s, p95 30.8 s in this run (Cloudflare timeouts); an earlier run had p50 2.1 s, p95 5.7 s | p95 < 2.5 s (ER-02) |

Model benchmark (same 12 questions, top-k 8):

| Model | Correct | p50 | p95 |
|---|---|---|---|
| `@cf/meta/llama-3.3-70b-instruct-fp8-fast` | 11/12 | 1.86 s | 3.88 s |
| `@cf/qwen/qwen3-30b-a3b-fp8` (chosen as default) | 10/12 | 0.76 s | 0.92 s |

Qwen3 was made the default because it is the only one under the 2.5 s p95 latency target; the accuracy gap was one question out of 12.

99-page `SplitPDF.pdf`, Qwen3, 4 questions (q01, q02, u01, s01): 129 chunks in 2.1 s; retrieval 2/2; all 4 passed (two cited answers, a correct refusal, spoiler limit held at page 60); p50 0.68 s, p95 0.82 s.

## Files (Steps 6-9)

### New
| File | Purpose |
|---|---|
| `backend/app/integrations/rag_ingestion.py` | Real `IngestionProvider`: pipeline + cleanup on delete |
| `backend/app/integrations/rag_retrieval.py` | Real `RetrievalProvider`, `list_chunks`, `format_passages` |
| `backend/app/integrations/grounded_answer.py` | Grounded `AnswerProvider` for all four interaction types |
| `backend/app/rag/extracted_store.py` | Saved per-page / per-chapter text for the reader |
| `backend/app/rag/prompts.py` | Prompt construction |
| `backend/app/rag/citations.py` | Citation, quote and copied-text checks; citation building |
| `backend/app/rag/llm.py` | Chat-model seam: Cloudflare model + offline fallback |
| `backend/scripts/eval_rag.py` | End-to-end evaluation and model benchmark |
| `backend/tests/eval/harry_potter_1.json`, `harry_potter_1_first99.json` | Labelled question sets |
| `backend/tests/test_ingestion_api.py` | Upload, ingestion status, reader text, delete, `/ready` through the API |
| `backend/tests/test_book_service.py` | Background job, restart recovery, column migration, dependency wiring |
| `backend/tests/rag/test_extracted_store.py`, `test_rag_ingestion.py` | Saved text store; ingestion provider outcomes |

### Modified
| File | Change |
|---|---|
| `backend/app/services/book_service.py` | Background ingestion, restart recovery, reader text, delete cleanup |
| `backend/app/services/ai_service.py` | Spoiler limit resolution, retrieval per interaction type, history, not-ready answers |
| `backend/app/api/v1/books.py` | Background task on upload; `/ingestion`; real `/content` |
| `backend/app/api/v1/ai.py` | Truthful `spoiler_scope` |
| `backend/app/api/deps.py` | Builds all real providers once; shared Cloudflare client; `reset_caches`, `close_resources` |
| `backend/app/main.py` | Startup recovery, real Qdrant check in `/ready`, shutdown cleanup |
| `backend/app/integrations/interfaces.py` | Pages on `RetrievedPassage`, resolved limit on `ReadingBoundary`, `chunk_count`, `provider_status`, `remove()`, `list_chunks()` |
| `backend/app/integrations/cloudflare.py` | `generate()`; per-call timeout / retries |
| `backend/app/integrations/mock_ai.py`, `mock_ingestion.py` | Fit the updated interfaces (no longer wired into the app) |
| `backend/app/rag/vector_store.py` | Embedded mode (`from_path`, `build_vector_store`), `list_chunks`, `ping`, `close`, lazy collection setup, lock for embedded mode |
| `backend/app/models/books.py`, `backend/app/db/database.py` | `chunk_count`, `ingestion_attempts`; `add_missing_columns` startup check |
| `backend/app/schemas/books.py`, `schemas/ai.py` | `chunk_count`; content / ingestion response fields; typed `Citation` |
| `backend/app/core/config.py` | New settings (below); invalid model ids fall back to the default |
| `backend/tests/conftest.py` | Forces the offline stack (fake embeddings, offline answers, in-memory Qdrant, temp text folder) even when `backend/.env` has credentials; upload helpers |
| `backend/tests/test_books.py`, `test_ai.py`, `test_config.py`, `test_health.py` | Five assertions updated because the behaviour changed on purpose: upload now returns `processing` (was `uploaded`); chat on a text-less book returns `unavailable` / `book_not_ready` (was a mock answer); `what_if` now runs on a real generated PDF; the text model has a default; `/ready` reports `vector_store` (was `qdrant: not_checked`) |
| `docker-compose.yml` | Qdrant always on; backend points at it and depends on it |
| `backend/.env.example`, `backend/README.md`, `README.md` | New settings, endpoints, setup, scripts |
| `docs/API_CONTRACT.md`, `docs/BACKEND_CONTEXT.md`, `docs/TEAM_INTEGRATION.md` | New and changed endpoints, citation shape, status, what each teammate needs |

### New settings (`backend/.env`)
| Variable | Default | Purpose |
|---|---|---|
| `CLOUDFLARE_TEXT_MODEL` | `@cf/qwen/qwen3-30b-a3b-fp8` | Chat model (Llama 3.3 is the alternative) |
| `ANSWER_BACKEND` | `auto` | `auto` / `cloudflare` / `fake` |
| `QDRANT_LOCAL_PATH` | `data/qdrant` | Embedded Qdrant folder when `QDRANT_URL` is blank |
| `EXTRACTED_DIR` | `data/extracted` | Saved reader text |
| `RETRIEVAL_TOP_K`, `RETRIEVAL_MIN_SCORE` | `8`, `0.5` | Passages per question; weaker matches dropped |
| `ANSWER_MAX_TOKENS`, `ANSWER_TIMEOUT_SECONDS` | `400`, `20` | Answer length; model timeout |
| `STORY_MAX_TOKENS`, `STORY_CONTEXT_CHUNKS` | `450`, `3` | `story_continues` length and context |
| `HISTORY_MAX_MESSAGES` | `6` | Earlier messages sent with a question |

## Testing (Steps 1-9)

```bash
cd backend
source .venv/bin/activate        # Python 3.11
pip install -r requirements.txt
pytest -q                        # 180 passed (5.8 s), fully offline
```

Live end-to-end check (uses Cloudflare quota; each run re-indexes the book):

```bash
python scripts/eval_rag.py --ids q01,q02,u01,s01 --show-answers   # 99-page SplitPDF.pdf, ~350-500 neurons
python scripts/eval_rag.py --show-answers                          # all 20 questions
python scripts/eval_rag.py "../Harry Potter, Book 1; The Sorcerer's Stone.pdf" --dataset tests/eval/harry_potter_1.json
```

Neither PDF is committed; both sit at the repo root locally.

## Known limitations and open items (Steps 6-9)

- **Latency (ER-02):** the default is now Qwen3, which met the 2.5 s p95 target in the benchmark (0.92 s) and in the 99-page run (0.82 s). The full-book evaluation table above was run with Llama 3.3, which misses the target; it has not been re-run with Qwen3. Confirm the model choice with the team (one line in `.env`).
- **Coverage:** the Step 6-8 code has tests (180 total pass), but no coverage report was run for Steps 6-9, and the new prompt, citation, retrieval, grounded-answer and chat-model modules have no dedicated unit tests yet (deliberately deferred). Steps 1-5 were measured at 100%.
- **Cloudflare quota:** the free plan allows 10,000 neurons per day. One full 250-page evaluation costs roughly 3,000-4,000; indexing a book once costs roughly 800 (250 pages) or 300-400 (99 pages). Embeddings are not cached yet, so re-uploading a book re-embeds it.
- **Retries on quota errors:** a 429 "daily free allocation used up" is retried like a normal rate limit, which wastes requests.
- **Faithfulness** is checked automatically (citations, verified quotes), not by a judge model.
- **Evaluation size:** 30 + 20 questions on one book, below the plan's 40-60 across 2-3 books.
- **Docker:** the compose file is validated (`docker compose config`), but `docker compose up --build` with ingestion end to end in the container has not been run.
- **Frontend:** the backend is ready, but the app does not yet call `/content` (reader still shows a sample passage) or `/ingestion`.
- **`story_continues` with no reading position** continues from the end of the indexed text (the "no limit" rule applies).
- **Team sign-off needed:** `what_if` and `story_continues` moved from Gitae to Umer; new interface fields affect Gitae; Qdrant always-on changes compose for everyone (Abinav); `/content`, `/ingestion` and the citation shape need Nievethan's frontend work.

---

# Steps 1-5: extraction through the Qdrant store (committed)

Adds the first half of the retrieval pipeline as standalone, tested library code:

```
PDF / EPUB -> extract -> clean -> chunk -> embed -> Qdrant
```

When Steps 1-5 were committed nothing was wired into the running app; Steps 6-9 (above) do that.

## How the pipeline works

| Stage | Module | What it does |
|---|---|---|
| Extract | `rag/extraction.py` | PDF: one `Section` per page, chapters from the PDF outline when present. EPUB: one `Section` per spine item (chapter = its number; nav page skipped). Detects scanned PDFs (`ScannedDocumentError`), encrypted or corrupt files (`ExtractionError`). |
| Clean | `rag/cleaning.py` | Removes running headers, footers and page numbers (PDF only), rejoins words hyphenated across lines, reflows hard-wrapped lines, normalises Unicode and control characters. Keeps section/page mapping 1:1. |
| Chunk | `rag/chunking.py` | Token-aware, paragraph-aligned chunks (default about 400 tokens, 12% sentence overlap). A chunk never crosses a chapter. Oversized paragraphs split on sentences, then words. Each chunk carries page range, chapter, `position` and `source_location`. |
| Embed | `rag/embeddings.py` | `EmbeddingProvider` protocol. Cloudflare Workers AI implementation (batched, bounded concurrency, dimension-checked) and a deterministic fake for tests and offline dev. `build_embedding_provider(settings)` picks one. |
| Store | `rag/vector_store.py` | One Qdrant collection for all books. `ensure_collection`, `upsert`, `search` (spoiler-bounded), `delete_book`, `count`. Pins the embedding model and dimension to the collection and refuses a mismatch. |
| HTTP client | `integrations/cloudflare.py` | Shared async Cloudflare client with retries (429/5xx/timeouts, `Retry-After`, exponential backoff). |

### Spoiler boundary

Every chunk has a `position`: the **last page** it touches (PDF) or its **chapter number** (EPUB). `search(..., max_position=N)` filters in the Qdrant query itself (`position <= N`), so a chunk is only returned if all of its text is at or before the reader. This replaces the roadmap's `max_order_index`: `order_index` is now just the chunk's sequence number.

## Files (Steps 1-5)

### New: application code (`backend/app/`)
- `rag/__init__.py`, `rag/models.py` (`Section`, `ExtractedDocument`, `Chunk`, `TocEntry`)
- `rag/extraction.py`, `rag/cleaning.py`, `rag/chunking.py`, `rag/embeddings.py`, `rag/vector_store.py`
- `integrations/cloudflare.py`
- `scripts/try_rag.py`: manual end-to-end check of Steps 1-5 on one book (written after the Steps 1-5 commit; still uncommitted, with the rest of `backend/scripts/`)

### New: tests (`backend/tests/`)
- `rag/conftest.py` (generates a small PDF, a blank "scanned" PDF and an EPUB; nothing copyrighted is committed)
- `rag/test_models.py`, `test_extraction.py`, `test_cleaning.py`, `test_chunking.py`, `test_embeddings.py`, `test_vector_store.py`
- `test_cloudflare.py`, `test_config.py`

### Modified
| File | Change |
|---|---|
| `backend/app/core/config.py` | Cloudflare and embedding settings, `qdrant_collection`, chunk size and overlap |
| `backend/.env.example` | Documents the new variables. Credentials stay blank. |
| `backend/requirements.txt` | Added `httpx` (now runtime), `pymupdf`, `EbookLib`, `beautifulsoup4`, `lxml`, `qdrant-client`; contains `pytest` |
| `backend/requirements-dev.txt` | Later deleted (commit "deleet reuiremnts-dev/txt"); `requirements.txt` is the single file. `pytest-cov` (used for coverage reports) is installed in the local venv but not listed. |
| `backend/README.md` | Setup steps reference `requirements.txt` only |
| `.gitignore` | Ignore `.coverage` and `htmlcov/` |

### Results at the time (Steps 1-5)
- 140 tests passed; **100%** line and branch coverage on `app/rag/*`, `app/integrations/cloudflare.py` and `app/core/config.py`.
- Harry Potter PDF, 250 pages: 312 chunks, max 397 tokens, overlap visible between chunks.
- Real Qdrant in Docker: upsert, spoiler-bounded search and delete by book worked; points visible in the dashboard.
- Live Cloudflare `@cf/baai/bge-base-en-v1.5`: 768-dim vectors, 312 chunks embedded in about 1.5 s; paraphrased questions landed on the correct pages.

## Behaviour notes and known limitations (Steps 1-5)
- Chapters come only from the PDF outline or the EPUB spine. There is no heading detection, so a PDF without an outline is one group with `chapter=None`. Spoiler filtering still works because PDFs use page numbers.
- A paragraph that continues across a PDF page break is split into two pieces joined by a blank line.
- Hidden text on cover pages (for example leftover OCR) can end up in the first chunk.
- A genuine compound split at a line break (`well-\nknown`) is rejoined as `wellknown`; a hyphen before a capital is kept.
- Token counts are an estimate (1.3 x words), not a real tokenizer.
- Scanned PDFs are rejected; OCR is out of scope.
- No BGE query-instruction prefix is applied to questions.
- `EMBEDDING_CONCURRENCY` / `EMBEDDING_BATCH_SIZE` are not yet confirmed against Cloudflare's documented batch limits.

## Decisions to confirm with the team (Steps 1-5)
1. `max_position` replaces `max_order_index` (see Spoiler boundary).
2. Embedding model `@cf/baai/bge-base-en-v1.5` at 768 dimensions.
