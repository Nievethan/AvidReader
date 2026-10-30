from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, register_request_logging
from app.db import database


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging()
    database.init_db()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="AvidReader Backend API", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
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
        """Truthful dependency readiness. Qdrant/Neo4j are optional and
        not yet wired to a real client, so they are reported as
        'configured or not' rather than falsely claimed as connected."""
        db_status = {"status": "ok"}
        try:
            with database.SessionLocal() as session:
                session.execute(text("SELECT 1"))
        except Exception as exc:  # pragma: no cover - defensive
            db_status = {"status": "error", "message": str(exc)}

        settings = get_settings()
        overall_ready = db_status["status"] == "ok"

        return {
            "status": "ready" if overall_ready else "degraded",
            "database": db_status,
            "optional_dependencies": {
                "qdrant": {
                    "configured": bool(settings.qdrant_url),
                    "status": "not_checked",
                    "note": "No vector retrieval client is wired in yet (Umer's work).",
                },
                "neo4j": {
                    "configured": bool(settings.neo4j_uri),
                    "status": "not_checked",
                    "note": "No character graph client is wired in yet (Gitae's work).",
                },
            },
        }

    return app


app = create_app()
