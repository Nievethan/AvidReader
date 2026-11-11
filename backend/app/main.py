from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import deps
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, register_request_logging
from app.db import database


logger = logging.getLogger("avidreader")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    database.init_db()
    # Ingestion jobs die with the process; resume any that were interrupted.
    service = deps.get_book_service()
    app.state.recovery_tasks = set()
    for book_id in service.recover_interrupted():
        logger.info("Resuming interrupted ingestion for book %s", book_id)
        task = asyncio.create_task(service.run_ingestion(book_id))
        app.state.recovery_tasks.add(task)  # keep a reference so it isn't garbage-collected
        task.add_done_callback(app.state.recovery_tasks.discard)
    try:
        yield
    finally:
        for task in list(app.state.recovery_tasks):
            task.cancel()
        await deps.close_resources()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="AvidReader Backend API", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        # `flutter run -d chrome` serves from a random localhost port, which
        # an exact-match origin list can't cover. Local dev only.
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$" if settings.is_local else None,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)
    register_request_logging(app)
    app.include_router(api_router)

    @app.get("/health", tags=["meta"])
    def health() -> dict:
        """Process-alive check only. Makes no claim about any database
        or external dependency -- see /ready for that."""
        return {"status": "ok"}

    @app.get("/ready", tags=["meta"])
    def ready() -> dict:
        """Truthful dependency readiness. Qdrant is checked for real (server,
        or embedded local mode when QDRANT_URL is blank). Neo4j is optional
        and not wired yet, so it is only reported as configured or not."""
        db_status = {"status": "ok"}
        try:
            with database.SessionLocal() as session:
                session.execute(text("SELECT 1"))
        except Exception as exc:  # pragma: no cover - defensive
            db_status = {"status": "error", "message": str(exc)}

        settings = get_settings()
        if settings.qdrant_url:
            qdrant_mode = "server"
        elif settings.qdrant_local_path == ":memory:":
            qdrant_mode = "memory"
        else:
            qdrant_mode = "local"
        qdrant_status = {"configured": True, "mode": qdrant_mode, "status": "ok"}
        try:
            deps.get_vector_store().ping()
        except Exception as exc:
            qdrant_status.update(status="error", message=f"{type(exc).__name__}: {exc}"[:300])

        overall_ready = db_status["status"] == "ok" and qdrant_status["status"] == "ok"

        return {
            "status": "ready" if overall_ready else "degraded",
            "database": db_status,
            "vector_store": qdrant_status,
            "optional_dependencies": {
                "neo4j": {
                    "configured": bool(settings.neo4j_uri),
                    "status": "not_checked",
                    "note": "No character graph client is wired in yet (Gitae's work).",
                },
            },
        }

    return app


app = create_app()
