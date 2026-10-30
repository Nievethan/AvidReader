# AvidReader Backend

FastAPI backend foundation for AvidReader. CPU-only, no paid AI keys and
no external database required to run or test locally.

## What's actually implemented right now

See [`../docs/BACKEND_CONTEXT.md`](../docs/BACKEND_CONTEXT.md) for the
authoritative implemented/mocked/planned breakdown. Summary: book
upload/catalog/progress with SQLite persistence, and a mock AI chat
endpoint. No real PDF/EPUB text extraction, retrieval, or LLM is wired
in yet -- those are explicit integration points for Umer and Gitae
(see [`../docs/TEAM_INTEGRATION.md`](../docs/TEAM_INTEGRATION.md)).

## Prerequisites

- Python 3.11 (matches the Dockerfile base image)
- No GPU, Docker, Qdrant, or Neo4j required for the foundation to run

## Local setup (manual, no Docker)

**Windows (PowerShell):**

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
copy .env.example .env
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Linux / macOS:**

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
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

Tests use an isolated temporary SQLite database and uploads directory
per test (see `tests/conftest.py`) -- they never touch your local
`backend/data/` directory. No network access or AI key is required.

Verified on this machine: **28/28 tests pass** (Python 3.11.9, Windows).

## Running with Docker Compose

```bash
docker compose up --build backend
```

Starts only the backend (CPU-only, SQLite, no external services). To
also start the optional Qdrant/Neo4j containers once Umer/Gitae need
them:

```bash
docker compose --profile full up --build
```

**Note:** the Docker path has not been executed on this development
machine (Docker is not installed here) -- the Compose file has been
corrected (GPU requirement removed, hardcoded Neo4j password removed)
but is unverified. Please run and confirm it on a machine with Docker
before relying on it for PR2 evidence.

## Environment variables

See `.env.example`. All have safe local defaults; nothing is required
to run the foundation. `QDRANT_URL` / `NEO4J_*` stay blank until
Umer/Gitae actually wire in those clients -- `/ready` reports them
honestly as "not configured" rather than claiming a connection.

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
│   ├── integrations/           # Protocols + mock providers for Umer/Gitae
│   └── api/v1/                 # route handlers
├── tests/
├── requirements.txt            # runtime deps only
├── requirements-dev.txt         # + pytest/httpx
└── main.py                      # compatibility shim -> app.main:app
```

## Known limitations (be honest about these)

- No Alembic migrations -- tables are created with `Base.metadata.create_all()`
  on startup. Fine for a prototype; revisit before any schema that needs
  real migrations.
- No authentication/multi-user model. Single implicit local user.
- No background/async ingestion job queue -- upload validation is
  synchronous; the ingestion provider hook is called inline as a stub.
- Docker Compose path is corrected but **not run-verified** on this
  machine (no Docker installed here).

## Troubleshooting

- **`ModuleNotFoundError: app`**: run commands from inside `backend/`,
  not the repo root.
- **Port 8000 already in use**: another `uvicorn` instance is likely
  still running; stop it or pass `--port 8001`.
- **Android emulator can't reach the API**: use `http://10.0.2.2:8000`
  as the base URL from the emulator, not `localhost`.
