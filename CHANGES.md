# Changes: AI character portraits (Visualize → Characters)

Owner: Umer. Branch: `Image-Generation`. Full design: `docs/CHARACTER_PORTRAITS_PLAN.md`.

## Summary

The Visualize → Characters screen used to show a plain Material icon for every
character, picked by role. It now shows a **photorealistic AI portrait** for each
character, generated with Cloudflare Workers AI's
`@cf/black-forest-labs/flux-1-schnell`. That model is hosted by Cloudflare (not
"Third-party"), so it runs on the free 10,000 neurons/day allowance. A
1024×1024 portrait at 8 steps costs about 96 neurons, so roughly 100
portraits/day fit in the free tier.

Rules:

1. **Generated once, kept forever.** Moving to a later chapter and tapping
   **Update** reuses each existing character's exact same image, with no model
   call. Portraits are stored in their own table and folder, separate from
   `character_graph_cache`, which Update still replaces wholesale.
2. **New characters get portraits on Update.** A character first introduced in a
   later chapter gets one image generated the next time the reader taps Update.
   Only characters without a portrait cost anything.
3. **No upgrades and no regenerate button.** If a later chapter describes a
   character in more detail, the existing portrait stays as it is (intentional).
4. **No spoilers and no actor likenesses.** The prompt is built only from an
   `appearance` description extracted from the text read so far. Every character
   name and the book title are scrubbed out, which also stops the model from
   copying a film actor's face (e.g. for Harry Potter).

**How it works:** `POST .../relationships/generate` extracts the graph as before,
then `PortraitService.sync()` matches each character to an existing portrait in
three steps:

1. **Exact match:** same `char_id`, or a stored alias of one.
2. **Name variant:** e.g. "Dudley" → "Dudley Dursley". This only happens when
   exactly one portrait matches. Titles count as name words, so "Mr. Dursley" and
   "Mrs. Dursley" never share a portrait, and an ambiguous "Dursley" gets its own.
3. **Otherwise:** the character is new, so a `pending` portrait row is created.

The response returns immediately. Images are generated in a FastAPI background
task, at most 2 at a time. A failed generation (rate limit, network) is marked
`failed`, never fails the Update, and is retried on the next Update. The app
shows a pulsing placeholder for pending portraits and re-checks the free cached
`GET /relationships` every 3 seconds (for up to 3 minutes) until they're ready.

**Live finding:** the Cloudflare docs example sends a `seed`, but the live
flux-1-schnell schema rejects any property other than `prompt` and `steps`, so
`generate_image()` sends only those two. This means a portrait isn't
reproducible from its prompt. That doesn't matter, because a ready portrait is
never regenerated and its saved JPEG is the source of truth.

## Backend

| File | Change |
|---|---|
| `app/integrations/cloudflare.py` | New `CloudflareClient.generate_image()`: `{prompt, steps}` → decodes `result.image` (base64 JPEG). Raises `CloudflareError` on a missing or invalid image. Reuses `run()` retries. |
| `app/integrations/character_graph.py` | Extraction prompt/shape now asks for `appearance`: a short, name-free visual description, using only details stated or clearly implied by the excerpts. Stored on each node (capped at 300 chars). |
| `app/integrations/portraits.py` (new) | `PortraitGenerator` protocol, `CloudflarePortraitGenerator`, offline `NotAvailablePortraitGenerator`, `build_portrait_prompt()` and `scrub_names()`, which removes name words, possessives and plurals ("Harry's", "Potters") and the book title. |
| `app/models/character_portrait.py` (new) | `character_portraits` table: PK `(book_id, char_id)`, `name`, `aliases_json`, `appearance`, `prompt` (exact text sent to Flux, for debugging), `image_path`, `status` (`pending`/`ready`/`failed`), `error`. Created by `create_all`, so no migration is needed. |
| `app/repositories/character_portrait_repository.py` (new) | CRUD plus alias lookup. |
| `app/services/portrait_service.py` (new) | Matching (`sync`), background generation (`run_jobs`, semaphore, in-memory de-dupe of active jobs), `attach` (fills `portrait_status`/`portrait_url` on response nodes), `portrait_file`, `delete_for_book`. |
| `app/schemas/character_map.py` | `CharacterNode` gains `appearance`, `portrait_status` (`none`/`pending`/`ready`/`failed`) and `portrait_url`. |
| `app/api/v1/character_map.py` | `GET /relationships` attaches portrait status. `POST /generate` syncs portraits and schedules jobs. **New** `GET /api/v1/books/{id}/characters/{char_id}/portrait` serves the JPEG (also resolves aliases) and returns 404 while pending or when there's no portrait. The URL carries `?v=<updated_at>`, so it's served with a long cache header. |
| `app/api/v1/router.py`, `app/api/deps.py`, `app/models/__init__.py` | Registered the new router, `get_portrait_generator()`/`get_portrait_service()` (Cloudflare when credentials are set, otherwise no portraits and the UI keeps icons), and the new model. |
| `app/services/book_service.py` | `DELETE /books/{id}` also deletes portrait rows and `PORTRAITS_DIR/{book_id}/`. |

## Frontend

| File | Change |
|---|---|
| `lib/models/character_map_item.dart` | `CharacterNode` gains `appearance`, `portraitStatus`, `portraitUrl`, `hasPortrait` and `portraitPending`. |
| `lib/api_client.dart` | `absoluteUrl(path)` helper for the relative `portrait_url`. |
| `lib/widgets/character_portrait.dart` (new) | Shows the image (fade-in, falls back to the icon on load error), a pulsing placeholder while pending, or the role icon for `none`/`failed`. |
| `lib/screens/visualize_screen.dart` | 132px portrait in the main character card with a "Painting portrait…" caption while pending, 44px round portraits in the "Characters in this chapter" strip, 3-second polling while any portrait is pending (stops when done, after 3 minutes, on book change or on dispose), and a snackbar like "Painting 2 new portraits…". |

## New settings (`backend/.env`)

| Variable | Default | Purpose |
|---|---|---|
| `CLOUDFLARE_IMAGE_MODEL` | `@cf/black-forest-labs/flux-1-schnell` | Text-to-image model |
| `PORTRAITS_DIR` | `./data/portraits` | Where portrait JPEGs are saved (`{book_id}/{char_id}.jpg`) |
| `PORTRAIT_STEPS` | `8` | Diffusion steps (clamped to 1–8; 8 is flux-1-schnell's max and best quality) |
| `PORTRAIT_CONCURRENCY` | `2` | Max portraits generated at once |
| `PORTRAIT_TIMEOUT_SECONDS` | `60` | Per-image request timeout |

## Testing

`pytest -q` → **233 passed** (217 existing + 16 new in
`tests/test_character_portraits.py`), fully offline using a stub
`PortraitGenerator` and stub chat model. `tests/conftest.py` now points
`PORTRAITS_DIR` at a temp folder. The new tests cover:

- a first Update generates every portrait
- **a later Update reuses existing images byte-for-byte and generates only the new character**
- name-variant reuse and alias resolution
- Mr./Mrs. never share a portrait, and an ambiguous name isn't guessed
- prompts contain no character names or book title
- a failed portrait is retried on the next Update without failing it
- the portrait endpoint returns 404s when it should
- deleting a book removes its portrait rows and files
- offline mode reports `portrait_status: "none"`
- `generate_image()` builds the right payload and rejects bad responses

`flutter analyze` is clean apart from one info-level lint in code that was
already there. The Flutter smoke test (`test/widget_test.dart`) fails on a
`RenderFlex` overflow in `progress_screen.dart`. That failure already exists on
the base commit without these changes.

## Known limitations

- **Realism depends on the text.** A character the book never physically
  describes gets a generic, but consistent, portrait.
- **Old cached graphs have no portraits.** Graphs cached before this change have
  no `appearance`, so the first Update afterwards generates portraits for all
  current characters.
- **Free daily limit:** the 10,000 neurons/day are shared with extraction,
  embeddings and Ask AI. When they run out, portraits are marked `failed`, the
  icons stay, and the next Update retries them.
- **In-process jobs:** background jobs run in the same process. If the server
  restarts mid-generation, the `pending` portraits are re-queued on the next
  Update.

---

# Changes: Frontend Full-Stack Integration (Character Map, Word Wall, Reading Log, Achievements)

Owner: Nievethan. Branch: `frontedn-hookup`.

## Summary

Previously, the Flutter frontend only consumed the basic book catalog, page content, and chat endpoints. The backend's new engagement and AI features—Character Map extraction, Word Wall CRUD, Reading Log streaks, and live Achievements—were not connected to the UI, and the Visualize and Progress screens displayed hardcoded static mock data.

This update fully wires the Flutter frontend to the FastAPI backend contract (`docs/API_CONTRACT.md`):

1. **Character Map & Relationships ([visualize_screen.dart](file:///home/nievethan/AvidReader/frontend/lib/screens/visualize_screen.dart))**:
   - Replaced static Crime & Punishment mockup with live data from `GET /api/v1/books/{id}/relationships`.
   - Added on-demand "Update" button calling `POST /api/v1/books/{id}/relationships/generate`, extracting grounded characters up to the reader's current page/chapter with zero spoilers.
   - Shows character role badges, descriptions, boundary tags, and direct relationships with verbatim evidence quotes.
   - Toggle between **Characters** profile view and **Relationships** connection graph list.

2. **Word Wall & Vocabulary ([progress_screen.dart](file:///home/nievethan/AvidReader/frontend/lib/screens/progress_screen.dart) & [reader_screen.dart](file:///home/nievethan/AvidReader/frontend/lib/screens/reader_screen.dart))**:
   - Integrated `GET`, `POST`, `DELETE /api/v1/books/{id}/words`.
   - Reader toolbar now has a **Word Wall** action dialog to save words, definitions, and page quotes.
   - AI passage explanations in the Reader include a one-tap **"Save to Word Wall"** button.
   - Dedicated Word Wall tab in Progress screen to browse, add, and delete entries.

3. **Reading Log, Streaks & Achievements ([progress_screen.dart](file:///home/nievethan/AvidReader/frontend/lib/screens/progress_screen.dart))**:
   - Fetches live streaks and reading calendar history (`GET /api/v1/reading-log`).
   - Displays all 6 live computed milestones (`GET /api/v1/achievements`) with unlocked/locked visual badges and descriptions.
   - Tabbed layout: Overview, Word Wall, Achievements, and Reading Log.

4. **Book Library & Deletion ([library_screen.dart](file:///home/nievethan/AvidReader/frontend/lib/screens/library_screen.dart) & [reading_dashboard_shell.dart](file:///home/nievethan/AvidReader/frontend/lib/screens/reading_dashboard_shell.dart))**:
   - Added book deletion (`DELETE /api/v1/books/{id}`) with confirmation modal, cascading through SQLite, Qdrant vectors, conversations, and Word Wall rows.
   - Resilient file picker: built `file_selector_service.dart` with automatic fallback to `zenity` (and manual file path entry) for Linux/WSL2 when XDG Desktop Portal is absent.

5. **AI Chat & Spoiler Guard ([ask_ai_screen.dart](file:///home/nievethan/AvidReader/frontend/lib/screens/ask_ai_screen.dart))**:
   - Added spoiler boundary notes (`spoiler_scope.reason`) to chat messages.
   - Added quick prompt chips ("What if…", "What happens next?", "Explain themes").

6. **Automated Testing ([widget_test.dart](file:///home/nievethan/AvidReader/frontend/test/widget_test.dart))**:
   - Updated fake backend test harness to mock `/relationships`, `/words`, `/reading-log`, and `/achievements`.

---

# Changes: character-map AI extraction

Owner: Abinav. Branch: `feature/character-map-ai-extraction` (built on top of
`feature/word-wall-achievements-charactermap-backend`, which added the
`not_available` placeholder route this replaces with real extraction).

## Summary

`GET /api/v1/books/{id}/relationships` previously always returned
`not_available` -- no extraction existed. Now `POST .../relationships/generate`
(the "Update" button) does real one-shot Cloudflare extraction over
everything the reader has read so far, grounds the result against the real
text, and caches it; `GET` just reads that cache for free. Not
auto-triggered on page load -- only the explicit Update action costs a
model call.

**Live-verified against a real uploaded book** (99-page Harry Potter PDF,
read to page 15, real Cloudflare credentials): returned 7 real character
nodes (Harry Potter, the Dursleys, Dumbledore, McGonagall, Hagrid, each with
a real `first_seen_chunk_id`) and 4 real grounded relationship edges, each
with a verbatim evidence quote checked against the actual book text. The
follow-up `GET` returned the same data in 44ms (cache hit).

**Two real bugs found and fixed by actually calling the real model** (not
visible in offline/mocked tests):
1. `CloudflareClient.generate()` (`app/integrations/cloudflare.py`, shared by
   everyone) treated `result["response"]` being present-but-not-a-string as
   "no answer text" and discarded it. Some models (Qwen3, on a JSON-mode
   prompt) put the already-parsed JSON object directly in `response` instead
   of a string -- a perfectly good answer was being thrown away. Fixed to
   prefer a string from either `response` or `choices[].message.content`, or
   serialize the object if that's all there is.
2. The model listed full names in `characters` (e.g. "Albus Dumbledore") but
   short names in `relationships` (e.g. "Dumbledore") -- exact-match name
   lookup silently dropped every single relationship edge, so the first live
   test returned 7 nodes and **zero** edges. Fixed with fuzzy name-word
   matching that still refuses to guess when a name word is ambiguous
   between two different characters (e.g. two people both named "Potter").

**A third orphan-cleanup bug, this one pre-dating this branch entirely:**
`DELETE /books/{id}` never cleaned up that book's `conversations`/`messages`
either (present since the original P0 chat feature, just never exercised by
a delete-after-chatting test until this pass). Fixed the same way as the
other two (`ai_repository.delete_for_book`), verified live (all of
`word_wall_entries`, `reading_log_entries`, `character_graph_cache`,
`conversations`, `messages` are actually empty in SQLite after a delete that
touched all of them), and covered by a new test.

**What this is NOT:** a finished, evaluated feature. It's a basic working
version -- one-shot over the whole read-so-far text, no per-chapter
incremental extraction or merging, no precision evaluation against PR2's
"≥85% precision across 40 reviewed connections" target, and a long or
mostly-read book could hit the model's context limit (not handled yet;
would need truncating to recent chunks or a chaptered approach). Good enough
to actually work and be demoed; not what PR2 describes as the final design.

**Testing:** `pytest -q` → 216 passed (200 existing + 4 Cloudflare-client
regression tests + 12 new character-map tests), fully offline -- the real
extraction path is tested via a dependency-injected stub chat model, not
real Cloudflare, so CI never needs credentials. Also live-verified end to
end as described above.

## New settings (`backend/.env`)
| Variable | Default | Purpose |
|---|---|---|
| `CHARACTER_MAP_MAX_TOKENS` | `4000` | Output budget for one extraction call (2000 was tried first and failed live -- see bug #1 above; this wasn't actually the cause, but headroom doesn't hurt) |
| `CHARACTER_MAP_TIMEOUT_SECONDS` | `45` | Per-call timeout (longer than chat's 20s default -- the prompt is much bigger) |

---



Two separate pieces of work:

1. **Frontend: closed the gap between the real RAG backend (below) and the
   Flutter app.** The Reader screen showed a hardcoded sample passage and
   never called the real endpoints; fixed to call `GET /content` and poll
   `GET /ingestion`. Found and fixed a page-offset bug during live browser
   testing: `currentPage` is 0-based in this app but `/content` is 1-based,
   so the first "next page" click looked broken (silently re-fetched the
   same page). Also fixed a stale `providerStatus == 'mock'` check in Ask AI
   (the backend never returns that value) and a stale "processing" banner
   that never refreshed after ingestion actually finished.
2. **Backend: Word Wall storage, reading log, achievements, and real wiring
   for the character-map route** -- none of these existed before. No AI
   involved; see `docs/API_CONTRACT.md` and `docs/TEAM_INTEGRATION.md` for
   full shapes and ownership notes.

| Feature | What it is |
|---|---|
| Word Wall | `POST`/`GET`/`DELETE /api/v1/books/{id}/words`. Plain CRUD: word + optional meaning/quote/source location, scoped per book. |
| Reading log | `GET /api/v1/reading-log`. Auto-logged (one row per book per UTC day) from every `PUT .../progress` call; computes `current_streak`/`longest_streak`. |
| Achievements | `GET /api/v1/achievements`. Six starter achievements, computed live from books/progress/reading-log/messages -- nothing persisted as "unlocked". |
| Character map | `GET /api/v1/books/{id}/relationships` is now real and wired (previously didn't exist at all), honestly returning `status: "not_available"` until Gitae's `CharacterGraphProvider` is implemented. |

**Testing:** `pytest -q` → 200 passed (187 existing + 13 new), fully offline,
no regressions. Also live-verified over real HTTP against the running
server (add/list/delete a word, a real progress update producing a
streak of 1, achievements flipping to `true` after a real upload and a
real chat message, the full `question`/`explain`/`what_if`/`story_continues`
matrix, cross-book conversation-mismatch 404, out-of-range/invalid-page
422/404s) -- not just unit tests.

**Bug found and fixed during a second, more adversarial test pass:**
`DELETE /api/v1/books/{id}` left that book's Word Wall entries and
reading-log rows behind as orphans (no cascade was wired up). Fixed in
`BookService.delete_book` via `engagement_repository.delete_for_book()`;
verified live (rows actually gone from SQLite after delete, not just a
204 response) and covered by a new regression test.

**Known limitations / honest gaps:**
- None of this is wired into the Flutter frontend yet (explicitly out of
  scope for this branch -- see `docs/TEAM_INTEGRATION.md`'s Nievethan
  section).
- Achievement IDs/thresholds are a reasonable starting design, not a
  reviewed final spec -- there was no detailed requirement beyond the name
  "achievements" anywhere in the project docs.
- Word Wall has no AI-generated meanings; the `meaning` field is just
  stored text, supplied by whoever calls the endpoint.
- EPUB path for reading log/achievements uses `current_chapter` the same
  way existing code does, but wasn't separately tested with a real EPUB
  (no sample file available locally).

---

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
