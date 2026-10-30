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

Interfaces to implement (in `app/integrations/interfaces.py`):

```python
class IngestionProvider(Protocol):
    async def ingest(self, book_id: str, file_path: str, file_type: str) -> IngestionResult: ...

class RetrievalProvider(Protocol):
    async def retrieve(
        self, book_id: str, question: str, reading_boundary: ReadingBoundary, limit: int = 5
    ) -> list[RetrievedPassage]: ...
```

- `IngestionResult.status` must be one of `uploaded`, `processing`,
  `ready`, `failed`, `unsupported` -- only say `ready` once content is
  genuinely retrievable.
- `RetrievedPassage` carries `chunk_id`, `text`, `source_location`,
  and `order_index` (used for spoiler filtering by reading position).
  Add a real relevance score when you have one.
- Currently wired: `MockIngestionProvider` (`app/integrations/mock_ingestion.py`),
  called synchronously from `BookService.upload_book` right after a
  file is stored. It always returns `status="uploaded"` and never
  fabricates a page count. **No `RetrievalProvider` is wired in at
  all yet** -- `AIService.chat` currently calls the answer provider
  with `sources=[]`. When you build a real retriever, it should be
  injected into `AIService` (see `app/api/deps.py::get_ai_service`)
  and called before `answer_provider.answer(...)`.
- To swap in your real implementation: write a class satisfying
  `IngestionProvider`/`RetrievalProvider`, then update
  `app/api/deps.py` to construct it instead of the mock. No changes
  needed in `app/api/v1/books.py` or `app/api/v1/ai.py`.
- Checkpoint/summary metadata to reduce token usage was discussed by
  the team but is **not implemented**. If you add it, it must not let
  a checkpoint bypass the spoiler boundary (i.e. summarize content the
  reader hasn't reached yet).

## Gitae -- AI generation / character graph

Interfaces to implement:

```python
class AnswerProvider(Protocol):
    async def answer(self, request: GenerationRequest, sources: list[RetrievedPassage]) -> GeneratedAnswer: ...

class CharacterGraphProvider(Protocol):
    async def get_graph(self, book_id: str, boundary: ReadingBoundary) -> GraphResult: ...
```

- `GenerationRequest` carries `question`, `mode`, `interaction_type`,
  `reading_boundary`, `selected_passage`, `explanation_level`.
- `GeneratedAnswer.answer_type` must be `"grounded"` when the answer
  is backed by real retrieved sources, `"hypothetical"` for creative
  interaction types (`what_if`, `story_continues`), never silently
  `"mock"` once you're live. `citations` must reference real
  `chunk_id`s from `sources` -- never invent one.
- Currently wired: `MockAnswerProvider` (`app/integrations/mock_ai.py`).
  Swap it in `app/api/deps.py::get_ai_service`.
- `CharacterGraphProvider` / `GET /api/v1/books/{book_id}/relationships`
  is **not implemented in this PR at all** -- it's defined as a
  Protocol only. Add the route under `app/api/v1/` plus a service when
  you're ready; follow the `not_available` pattern used by
  `GET /api/v1/books/{book_id}/content` until real extraction exists.
  If you seed fixture data for demos, mark it `source: "fixture"`, not
  `"extracted"`.
- Image/portrait generation has no hook yet. Add one the same way:
  Protocol in `interfaces.py`, mock in `integrations/`, wired via
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
- Nothing in `frontend/` was touched by this PR -- no refactor, no new
  HTTP client dependency added. Wiring `main.dart` to these endpoints
  is a follow-up, not part of this backend-foundation PR.

## Arno -- QA / CI

- Tests: `cd backend && python -m pytest -v` (currently 28/28 passing,
  Python 3.11.9). No network access or AI key required -- everything
  runs against an isolated temp SQLite DB per test
  (`backend/tests/conftest.py`).
- `GET /health` (process) and `GET /ready` (DB + optional-dependency
  status) are both implemented and tested.
- Docker: `docker compose up --build backend` for CPU-only; add
  `--profile full` to also start Qdrant/Neo4j once they're needed.
  **This Docker path has not been run on the development machine used
  for this PR (no Docker installed there) -- please verify it in CI or
  on your own machine before treating it as confirmed.**
- Known gap for CI: no GitHub Actions workflow exists yet in this
  repo. Suggested minimal job: checkout -> setup Python 3.11 -> `pip
  install -r backend/requirements-dev.txt` -> `pytest -v` from
  `backend/`.
