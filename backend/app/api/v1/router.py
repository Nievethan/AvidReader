from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import achievements, ai, books, character_map, reading, reading_log, words

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(books.router)
api_router.include_router(reading.router)
api_router.include_router(ai.router)
api_router.include_router(words.router)
api_router.include_router(character_map.router)
api_router.include_router(reading_log.router)
api_router.include_router(achievements.router)
