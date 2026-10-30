from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import ai, books, reading

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(books.router)
api_router.include_router(reading.router)
api_router.include_router(ai.router)
