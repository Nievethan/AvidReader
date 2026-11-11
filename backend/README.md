# AvidReader Backend

FastAPI backend for AvidReader. CPU-only. Runs and tests with no paid AI
keys and no Docker; with Cloudflare Workers AI credentials it gives real,
cited answers grounded in the uploaded book.

## What's implemented

See [`../docs/BACKEND_CONTEXT.md`](../docs/BACKEND_CONTEXT.md) for the full
breakdown. Summary:

- Book upload/catalog/progress with SQLite persistence.
- **RAG pipeline (Umer):** uploads are indexed in the background
  (extract -> clean -> chunk -> embed -> Qdrant); the reader gets the real
  page/chapter text; chat retrieves passages up to the reader's position and
  answers with page citations (`question`, `explain`, `what_if`,
  `story_continues`). See [RAG pipeline](#rag-pipeline) below.
- Not yet: character graph / Neo4j and Gitae's feature endpoints
  (see [`../docs/TEAM_INTEGRATION.md`](../docs/TEAM_INTEGRATION.md)).

## Prerequisites

- Python 3.11 (matches the Dockerfile base image; 3.14 cannot build the
  pinned pydantic)
- No GPU, Docker or Neo4j required. Qdrant runs embedded when `QDRANT_URL`
  is blank.
- Optional: a Cloudflare account with Workers AI (account id + API token)
  for real embeddings and answers.

## Local setup (manual, no Docker)

**Windows (PowerShell):**

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
copy .env.example .env
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Linux / macOS:**

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Then open:

- Swagger UI: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/health
- Readiness: http://127.0.0.1:8000/ready

`main.py` at the repo root of `backend/` still works as a compatibility
shim (`uvicorn main:app`), but `app.main:app` is the canonical path.

## Running tests

```bash
python -m pytest -v
```

Tests use an isolated temporary SQLite database, uploads directory and
text folder per test, an in-memory Qdrant, fake embeddings and the offline
answer model (see `tests/conftest.py`). They never touch `backend/data/`
and never call Cloudflare, even when `backend/.env` has credentials.

## Running with Docker Compose

```bash
docker compose up --build            # backend + Qdrant
docker compose --profile full up     # also starts Neo4j
```

Qdrant always starts (book vectors live there); the backend container uses
`QDRANT_URL=http://qdrant:6333`. Cloudflare credentials are read from
`backend/.env`, which is mounted with the code. Qdrant's dashboard is at
http://localhost:6333/dashboard. After changing `requirements.txt`, rebuild
with `docker compose build backend`.

## Environment variables

See `.env.example`; every value has a safe default and nothing is required
to start. The important ones:

| Variable | Default | Purpose |
|---|---|---|
| `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN` | blank | Workers AI credentials. Blank = offline fallbacks |
| `CLOUDFLARE_TEXT_MODEL` | `@cf/meta/llama-3.3-70b-instruct-fp8-fast` | Chat model for answers (invalid values fall back to the default) |
| `CLOUDFLARE_EMBEDDING_MODEL`, `EMBEDDING_DIMENSION` | `@cf/baai/bge-base-en-v1.5`, `768` | Embedding model; pinned to the Qdrant collection |
| `EMBEDDING_BACKEND`, `ANSWER_BACKEND` | `auto` | `auto` / `cloudflare` / `fake` |
| `QDRANT_URL` | blank | Qdrant server. Blank = embedded Qdrant in `QDRANT_LOCAL_PATH` |
| `QDRANT_LOCAL_PATH` | `data/qdrant` | Embedded Qdrant folder (`:memory:` for RAM only) |
| `EXTRACTED_DIR` | `data/extracted` | Cleaned page/chapter text served to the reader |
| `CHUNK_TARGET_TOKENS`, `CHUNK_OVERLAP_RATIO` | `400`, `0.12` | Chunk size and overlap |
| `RETRIEVAL_TOP_K`, `RETRIEVAL_MIN_SCORE` | `8`, `0.5` | Passages per question; weaker matches are dropped |
| `ANSWER_MAX_TOKENS`, `ANSWER_TIMEOUT_SECONDS` | `400`, `20` | Answer length and model timeout |
| `STORY_MAX_TOKENS`, `STORY_CONTEXT_CHUNKS` | `450`, `3` | `story_continues` length and context |
| `HISTORY_MAX_MESSAGES` | `6` | Earlier messages sent with a question |

Leave a variable out rather than present-but-empty (an empty
`EMBEDDING_DIMENSION=` fails to parse).

## RAG pipeline

```
upload ─► 201 {processing_status: "processing"}
  └─ background: extract ─► clean ─► chunk ─► embed ─► Qdrant (+ saved page text)
         status: processing ─► ready | unsupported (scanned PDF) | failed
chat ─► reading boundary ─► retrieve (Qdrant, position <= boundary) ─► chat model ─► citation checks
```

**Endpoints added or changed** (full shapes in `../docs/API_CONTRACT.md`):

| Endpoint | What it does |
|---|---|
| `POST /api/v1/books` | Stores the file, returns at once with `processing`; indexing runs in the background |
| `GET /api/v1/books/{id}/ingestion` | `{status, message, total_pages, chunk_count, attempts, updated_at}` |
| `GET /api/v1/books/{id}/content?page=N` / `?chapter=N` | Real cleaned text of one page (PDF) or chapter (EPUB) |
| `DELETE /api/v1/books/{id}` | Also deletes the book's vectors and saved text (works even if Qdrant is down) |
| `POST /api/v1/ai/chat` | Grounded answer with `citations` and a truthful `spoiler_scope` |
| `GET /ready` | Real Qdrant check under `vector_store` |

**Spoiler boundary:** page for PDFs, chapter for EPUBs. Taken from the
chat request's `reading_position`, else the saved reading progress, else no
limit (and `spoiler_scope` says so). It is applied inside the Qdrant query.

**Answer types:** `grounded` (cited facts), `hypothetical` (`what_if`,
`story_continues`), `refusal` (not in the part of the book read so far),
`unavailable` (book not ready, or the model failed). Every answer is checked:
invalid `[S#]` markers are dropped, quotes not found in the excerpts lose
their quote marks, copied sentences are removed from story continuations,
and a factual answer with no valid citation becomes a refusal.

**Restart safety:** a book left in `processing` by a server restart is
re-indexed once automatically on startup; if that is interrupted too it is
marked `failed`.

### Try it

```bash
# backend running on :8000; any PDF path works
BOOK_ID=$(curl -s -F "file=@/path/to/book.pdf" localhost:8000/api/v1/books \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
curl -s localhost:8000/api/v1/books/$BOOK_ID/ingestion          # until "ready"
curl -s "localhost:8000/api/v1/books/$BOOK_ID/content?page=3"
curl -s localhost:8000/api/v1/ai/chat -H 'Content-Type: application/json' -d "{
  \"book_id\": \"$BOOK_ID\", \"question\": \"Who is the main character?\",
  \"reading_position\": {\"current_page\": 20}}" | python3 -m json.tool
```

### Scripts

| Script | Purpose |
|---|---|
| `scripts/try_rag.py BOOK [--embedder cloudflare] [--qdrant URL]` | Steps 1-5 on one book, printed stage by stage |
| `scripts/eval_rag.py [BOOK] [--dataset FILE] [--ids q01,u01] [--models a,b] [--report out.json]` | End-to-end evaluation through the real API: ingestion speed, retrieval hit@k, answer accuracy, refusals, spoiler safety, latency. `--models` benchmarks several chat models on the same questions. Default: the 99-page `SplitPDF.pdf` at the repo root with `tests/eval/harry_potter_1_first99.json` (cheapest); `tests/eval/harry_potter_1.json` is the full 250-page book. Each run re-indexes the book (about 300-400 Cloudflare neurons for the 99-page file, about 800-900 for the full book) |

## Project layout

```text
backend/
├── app/
│   ├── main.py              # app factory, /health, /ready
│   ├── core/                # config, errors, logging
│   ├── db/                  # SQLAlchemy engine/session, init_db()
│   ├── models/               # ORM models (Book, BookProgress, Conversation, Message)
│   ├── schemas/               # Pydantic request/response DTOs
│   ├── repositories/          # DB access functions
│   ├── services/              # business logic (upload validation, progress, AI orchestration)
│   ├── integrations/           # Protocols, Cloudflare client, RAG providers (+ mocks)
│   ├── rag/                    # extraction, cleaning, chunking, embeddings, vector store,
│   │                           # prompts, citation checks, chat-model seam, saved text
│   └── api/v1/                 # route handlers
├── scripts/                     # try_rag.py, eval_rag.py
├── tests/                       # unit/API tests; tests/eval/ = labelled question sets
├── requirements.txt            # app + test dependencies (incl. pytest)
└── main.py                      # compatibility shim -> app.main:app
```

## Known limitations (be honest about these)

- No Alembic migrations -- tables are created with `Base.metadata.create_all()`
  on startup. Fine for a prototype; revisit before any schema that needs
  real migrations.
- No authentication/multi-user model. Single implicit local user.
- Ingestion uses FastAPI `BackgroundTasks` (in-process, one server). Jobs
  interrupted by a restart are retried once at startup; there is no
  distributed queue.
- Embedded Qdrant (blank `QDRANT_URL`) allows one process per folder: don't
  point `scripts/try_rag.py` at the server's folder while it runs.
- Scanned PDFs are rejected (no OCR). Chapters come only from the PDF outline
  or EPUB spine.
- Faithfulness is enforced with automatic checks (citations, verified
  quotes), not a judge model.

## Troubleshooting

- **`ModuleNotFoundError: app`**: run commands from inside `backend/`,
  not the repo root.
- **Port 8000 already in use**: another `uvicorn` instance is likely
  still running; stop it or pass `--port 8001`.
- **Android emulator can't reach the API**: use `http://10.0.2.2:8000`
  as the base URL from the emulator, not `localhost`.
