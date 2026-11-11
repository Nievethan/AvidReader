# Backend Context (current state)

Code-focused status of the backend only. Last verified: 2026-10-30, on
branch `feature/backend-foundation`, Python 3.11.9, Windows.

## Keeping this file accurate (read this before you change backend code)

This file, `API_CONTRACT.md`, and `TEAM_INTEGRATION.md` are the fast
path for anyone on the team -- or their own Claude/AI session -- to see
what's real vs. mocked without reading all the code first. If you (or
your AI assistant) change backend behavior, **update the relevant
table row/section in the same commit or PR**, not as a follow-up:

- Swapped a mock for a real provider (e.g. real retrieval, real LLM)? Move it from "Explicitly mocked" to "Implemented and tested" below, and update its `Protocol` usage note in `TEAM_INTEGRATION.md`.
- Added/changed an endpoint? Update `API_CONTRACT.md` with the real request/response shape, and move it out of "Not implemented at all yet" here if it was listed.
- Found something in this file that's already wrong/stale? Fix it and add a dated line to the change log below -- don't leave it silently inaccurate for the next person (or the next AI session) to trip over.

## Change log

| Date | Who/what changed | Summary |
|---|---|---|
| 2026-10-30 | Abinav (backend foundation PR, via Claude) | Initial P0 foundation: health/ready, book upload/catalog, progress, mock AI chat + conversations, typed integration Protocols, tests, Docker/Compose fixes. |
| 2026-11-11 | Umer (RAG Steps 1-9, via Claude) | Real ingestion (background, status route, restart recovery), reader text, Qdrant (server or embedded), retrieval with spoiler boundary, grounded answers on Cloudflare Workers AI with citation checks, `eval_rag.py` evaluation. Mocks replaced for ingestion and chat. |

## Implemented and tested (real, working code)

| Area | What exists | File(s) |
|---|---|---|
| App factory / lifespan | Creates tables on startup, mounts CORS, registers error handlers + request logging | `app/main.py` |
| Health/readiness | `GET /health` (process only), `GET /ready` (real DB check + real Qdrant check under `vector_store`; Neo4j reported as configured or not) | `app/main.py` |
| Book upload | Validates real file content (PDF magic bytes / EPUB zip+mimetype), rejects bad/oversized/wrong-type files, sanitizes filenames, stores to disk, persists metadata row | `app/services/book_service.py`, `app/services/file_validation.py` |
| Book catalog | List / get / delete, correct status codes (404 on missing) | `app/api/v1/books.py` |
| Book content | `GET /books/{id}/content?page=N|chapter=N`: real cleaned page (PDF) or chapter (EPUB) text saved at ingestion | `app/api/v1/books.py`, `app/rag/extracted_store.py` |
| Reading progress | Get/update, persisted in SQLite, validated (page >= 0, 0-100%) | `app/api/v1/reading.py`, `app/services/progress_service.py` |
| AI chat (grounded) | Retrieval up to the reader's boundary (request position -> saved progress -> none), Cloudflare chat model, `[S#]` citation validation, quote verification, refusal when unsupported; `question`/`explain`/`what_if`/`story_continues`; truthful `spoiler_scope` | `app/services/ai_service.py`, `app/integrations/rag_retrieval.py`, `app/integrations/grounded_answer.py`, `app/rag/prompts.py`, `app/rag/citations.py`, `app/rag/llm.py` |
| Ingestion | Background job on upload (extract, clean, chunk, embed, Qdrant), `processing -> ready/unsupported/failed`, `GET /books/{id}/ingestion`, retry-once restart recovery, delete removes vectors + text | `app/integrations/rag_ingestion.py`, `app/services/book_service.py`, `app/rag/` |
| Conversation retrieval | `GET /api/v1/ai/conversations/{id}` returns full message history | `app/api/v1/ai.py` |
| Persistence | SQLite via SQLAlchemy; `books` gained `chunk_count` and `ingestion_attempts` (added to existing databases at startup by `add_missing_columns`) | `app/db/database.py`, `app/models/` |
| Tests | Offline suite (fake embeddings, offline answer model, in-memory Qdrant) plus `scripts/eval_rag.py` for live end-to-end evaluation; see `backend/README.md` | `backend/tests/`, `backend/scripts/` |
| Integration contracts | `Protocol`s for Umer (`IngestionProvider`, `RetrievalProvider`) and Gitae (`AnswerProvider`, `CharacterGraphProvider`), with mock implementations wired in | `app/integrations/interfaces.py` |

**Verification performed this session:**
- `pytest -v` → 28 passed (includes edge cases: oversized upload → 413, wrong-content-despite-correct-extension → 415, corrupt/non-EPUB zip, path-traversal filename sanitization, cross-book conversation mismatch → 404, file actually removed from disk on delete).
- Live server started with `uvicorn app.main:app`; hit `/health`, `/ready`, `/docs` over real HTTP.
- Full flow over real HTTP (curl): upload PDF → list → update progress → AI chat → fetch conversation. All returned expected data.
- Restarted the server and re-listed books: data persisted correctly.

## Explicitly mocked (labeled as such in the API, not hidden)

- **Offline fallbacks** (only without Cloudflare credentials, or with `EMBEDDING_BACKEND`/`ANSWER_BACKEND=fake`): hash-based fake embeddings and an extractive offline answer model. Offline answers are prefixed `[Offline answer, no AI model configured]` and report `provider_status: "fake"`.
- `MockIngestionProvider` / `MockAnswerProvider` still exist for tests but are no longer wired into the app.

## Not implemented at all yet (planned, not built)

- Word Wall (`/books/{id}/words`)
- Character/relationship graph (`/books/{id}/characters`, `/relationships`)
- Reading sessions / activity log / achievements
- Visualization / image generation endpoints
- Study mode (quizzes/flashcards)
- Alembic migrations (using `create_all()` instead -- fine for now, documented limitation)
- Authentication / multi-user model

## Blocked / needs verification elsewhere

- **Docker Compose**: Qdrant now always starts and the backend uses `QDRANT_URL=http://qdrant:6333` (`docker compose config` validated on 2026-11-11; the Qdrant container was run and used for vector-store testing). A full `docker compose up --build` of the new backend image with ingestion end to end has not been run yet.
- No CI workflow exists in the repo yet (Arno's area).
- Frontend: connected for upload/library/chat (`frontend/lib/api_client.dart`). It does not yet call `GET /books/{id}/content` (the reader still shows a sample passage) or `GET /books/{id}/ingestion`.

## Quick facts for anyone resuming this work

- Branch: `feature/backend-foundation` (not merged to `main`).
- Run locally: see `backend/README.md`.
- Canonical entry point: `app.main:app` (root `backend/main.py` is a compatibility shim only).
- DB: SQLite at `backend/data/avidreader.db`, uploads at `backend/data/uploads/` -- both gitignored, neither committed.
