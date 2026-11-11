# Team Integration Guide

How each teammate plugs into the backend without rewriting route
handlers. The API layer (`app/api/v1/*.py`) only ever depends on the
`Protocol` interfaces in `app/integrations/interfaces.py` -- never on
a concrete provider -- so swapping a mock for a real implementation is
a one-file change plus a dependency wire-up in `app/api/deps.py`.

**When you change a `Protocol` signature or swap your real
implementation in, update this file and `docs/API_CONTRACT.md` in the
same PR**, and move your area from "mocked" to "implemented" in
`docs/BACKEND_CONTEXT.md`. Everyone else -- and their own AI
assistant, which has no other way to know -- relies on these three
docs staying truthful and current.

## Umer -- document ingestion / retrieval

**Status (2026-11-11): implemented and wired** (`app/api/deps.py`).

| Piece | Implementation |
|---|---|
| `IngestionProvider` | `RagIngestionProvider` (`app/integrations/rag_ingestion.py`): extract -> clean -> chunk -> embed -> Qdrant, plus cleaned text for the reader. Runs as a background job started by `POST /books`; `BookService.run_ingestion` records the result. |
| `RetrievalProvider` | `RagRetrievalProvider` (`app/integrations/rag_retrieval.py`): `retrieve()` (top-k, spoiler-bounded) and `list_chunks()` (every passage up to the boundary in reading order, or the last n). |
| `AnswerProvider` | `GroundedAnswerProvider` (`app/integrations/grounded_answer.py`) for `question`, `explain`, `what_if` and `story_continues`. |
| Shared Cloudflare client | `app/integrations/cloudflare.py`: async `embed()` and `generate()` with retries and per-call timeouts. |

- **Spoiler boundary:** `ReadingBoundary.limit` = page (PDF) or chapter
  (EPUB). `AIService.resolve_boundary` takes it from the request, else the
  saved progress, else none. Qdrant filters on it (`position <= limit`).
- **Contract changes:** `RetrievedPassage` gained `page_start`,
  `page_end`, `chapter`, `chapter_title`; `IngestionResult` gained
  `chunk_count`; `GeneratedAnswer` gained `provider_status`;
  `IngestionProvider` gained `remove(book_id)`; `RetrievalProvider`
  gained `list_chunks()`.
- **Evaluation:** `backend/scripts/eval_rag.py` (see `backend/README.md`).
- Checkpoint/summary metadata is still **not implemented**; if added it
  must not bypass the spoiler boundary.

## Gitae -- AI generation / character graph

Interfaces to implement:

```python
class AnswerProvider(Protocol):
    async def answer(self, request: GenerationRequest, sources: list[RetrievedPassage]) -> GeneratedAnswer: ...

class CharacterGraphProvider(Protocol):
    async def get_graph(self, book_id: str, boundary: ReadingBoundary) -> GraphResult: ...
```

- **Ownership change (agreed 2026-11-11):** `what_if` and
  `story_continues` are now handled by Umer's `GroundedAnswerProvider`.
  Gitae keeps `character_map`, `word_wall`, `environment` and
  `spoiler_guard`.
- **What to reuse for your features:**
  - `CloudflareClient.generate(model, messages, max_tokens=...)` from
    `app/integrations/cloudflare.py`. It is async, so it won't freeze the API like
    the prototype's blocking `httpx.post`. Get the shared instance from
    `app/api/deps.py::get_cloudflare_client()`.
  - `RagRetrievalProvider.list_chunks(book_id, boundary)` for spoiler-safe
    coverage of the book (character map, environment), and
    `format_passages(passages)` for the numbered `[S1] (page 12)` block.
  - Citation helpers in `app/rag/citations.py` (`check_answer`,
    `build_citations`) so your features return the same citation shape.
- `GeneratedAnswer.answer_type` is `grounded` / `hypothetical` /
  `refusal` / `unavailable`; `citations` reference real `chunk_id`s.
  Citation shape: see `docs/API_CONTRACT.md`.
- Structured feature output (character lists etc.) does not fit
  `ChatResponse`; add new routes under `app/api/v1/` for those.
- `CharacterGraphProvider` / `GET /api/v1/books/{book_id}/relationships`
  is still **not implemented**. Follow the `not_available` pattern until
  real extraction exists. Mark demo fixture data `source: "fixture"`.
- Image/portrait generation has no hook yet. Add one the same way:
  Protocol in `interfaces.py`, implementation in `integrations/`, wired via
  `deps.py`.

## Nievethan -- frontend integration

- Full request/response examples: `docs/API_CONTRACT.md`. Also live
  at `http://127.0.0.1:8000/docs` while the server is running.
- Base URL by environment: `http://localhost:8000` from a desktop
  browser or iOS simulator; `http://10.0.2.2:8000` from the Android
  emulator; your machine's LAN IP (and a firewall rule) for a physical
  device. None of this is hardcoded in the backend.
- Upload: `multipart/form-data`, field name `file`, optional `title`/`author` fields.
- `mode` values in the chat request (`study`/`research`/`creative`)
  match the filter pills already in `Ask AI` in `main.dart`.
- **New for the frontend (backend ready, frontend not yet wired):**
  - After upload, `processing_status` is `processing`; poll
    `GET /api/v1/books/{id}/ingestion` until `ready` / `unsupported` /
    `failed` and show `message` on failure.
  - Reader text: `GET /api/v1/books/{id}/content?page=N` (PDF) or
    `?chapter=N` (EPUB) returns `{content, index, total, title}`; this can
    replace the sample passage in the reader.
  - Chat: always send `reading_position` (page for PDF, chapter for EPUB).
    Citations now carry `page` (the existing `'p. N'` chip keeps working),
    plus `page_end`, `chapter`, `snippet` and `marker` (matches `[S1]` in
    the answer text). Show `spoiler_scope.reason` if useful, and treat
    `answer_type` `refusal`/`unavailable` as non-errors.

## Arno -- QA / CI

- Tests: `cd backend && python -m pytest`. Fully offline: fake
  embeddings, offline answer model, in-memory Qdrant, temp DB/uploads/text
  per test (`backend/tests/conftest.py`), even if `backend/.env` holds
  Cloudflare credentials.
- Live end-to-end check (needs Cloudflare credentials and a book):
  `python scripts/eval_rag.py "/path/to/book.pdf"`. The Harry Potter
  question set is in `backend/tests/eval/harry_potter_1.json`; the PDF
  itself is not committed.
- `GET /health` (process) and `GET /ready` (DB + real Qdrant check).
- Docker: `docker compose up --build` starts the backend and Qdrant;
  `--profile full` adds Neo4j.
- Known gap for CI: no GitHub Actions workflow exists yet in this
  repo. Suggested minimal job: checkout -> setup Python 3.11 -> `pip
  install -r backend/requirements.txt` -> `pytest -v` from
  `backend/`.
