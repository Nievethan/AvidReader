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

## Implemented and tested (real, working code)

| Area | What exists | File(s) |
|---|---|---|
| App factory / lifespan | Creates tables on startup, mounts CORS, registers error handlers + request logging | `app/main.py` |
| Health/readiness | `GET /health` (process only), `GET /ready` (real DB check + honest optional-dependency reporting) | `app/main.py` |
| Book upload | Validates real file content (PDF magic bytes / EPUB zip+mimetype), rejects bad/oversized/wrong-type files, sanitizes filenames, stores to disk, persists metadata row | `app/services/book_service.py`, `app/services/file_validation.py` |
| Book catalog | List / get / delete, correct status codes (404 on missing) | `app/api/v1/books.py` |
| Book content | Honest `not_available` placeholder (no fabricated text) | `app/api/v1/books.py` |
| Reading progress | Get/update, persisted in SQLite, validated (page >= 0, 0-100%) | `app/api/v1/reading.py`, `app/services/progress_service.py` |
| AI chat (mock) | Accepts book/mode/interaction_type/position/passage, persists conversation + messages, returns clearly labeled mock answer, empty citations, hypothetical flag for creative modes | `app/api/v1/ai.py`, `app/services/ai_service.py`, `app/integrations/mock_ai.py` |
| Conversation retrieval | `GET /api/v1/ai/conversations/{id}` returns full message history | `app/api/v1/ai.py` |
| Persistence | SQLite via SQLAlchemy, survives server restart (verified manually) | `app/db/database.py`, `app/models/` |
| Tests | 28/28 passing, isolated temp DB/uploads per test, no network/AI key needed | `backend/tests/` |
| Integration contracts | `Protocol`s for Umer (`IngestionProvider`, `RetrievalProvider`) and Gitae (`AnswerProvider`, `CharacterGraphProvider`), with mock implementations wired in | `app/integrations/interfaces.py` |

**Verification performed this session:**
- `pytest -v` → 28 passed (includes edge cases: oversized upload → 413, wrong-content-despite-correct-extension → 415, corrupt/non-EPUB zip, path-traversal filename sanitization, cross-book conversation mismatch → 404, file actually removed from disk on delete).
- Live server started with `uvicorn app.main:app`; hit `/health`, `/ready`, `/docs` over real HTTP.
- Full flow over real HTTP (curl): upload PDF → list → update progress → AI chat → fetch conversation. All returned expected data.
- Restarted the server and re-listed books: data persisted correctly.

## Explicitly mocked (labeled as such in the API, not hidden)

- **AI answers**: `answer_type`/`provider_status` always say `"mock"` (or `"hypothetical"` for creative interaction types). `citations` is always `[]`. No real LLM or RAG is called.
- **Ingestion**: `MockIngestionProvider` just confirms the file was stored. `processing_status` stays `"uploaded"` -- never claims `"ready"` or a real page count.
- **Spoiler protection**: `spoiler_scope.restricted_to_progress` is always `false` with an explicit reason, because no retrieval boundary is enforced yet.

## Not implemented at all yet (planned, not built)

- Word Wall (`/books/{id}/words`)
- Character/relationship graph (`/books/{id}/characters`, `/relationships`)
- Reading sessions / activity log / achievements
- Visualization / image generation endpoints
- Study mode (quizzes/flashcards)
- Real retrieval (`RetrievalProvider` has no implementation wired in -- `AIService` currently calls the answer provider with `sources=[]`)
- Alembic migrations (using `create_all()` instead -- fine for now, documented limitation)
- Authentication / multi-user model

## Blocked / needs verification elsewhere

- **Docker Compose path is corrected but unverified** (GPU requirement removed, hardcoded Neo4j password removed, Qdrant/Neo4j moved behind a `full` profile) -- this dev machine has no Docker installed, so `docker compose up` itself has not been run. Needs confirmation on a machine with Docker, or in CI.
- No CI workflow exists in the repo yet (Arno's area).
- Frontend (`frontend/`) was not touched and is not connected to any of this -- `main.dart` still has no HTTP client call anywhere.

## Quick facts for anyone resuming this work

- Branch: `feature/backend-foundation` (not merged to `main`).
- Run locally: see `backend/README.md`.
- Canonical entry point: `app.main:app` (root `backend/main.py` is a compatibility shim only).
- DB: SQLite at `backend/data/avidreader.db`, uploads at `backend/data/uploads/` -- both gitignored, neither committed.
