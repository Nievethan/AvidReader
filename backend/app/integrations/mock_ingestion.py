"""Placeholder IngestionProvider used until Umer's real parser exists.

Deliberately does NOT claim pages were parsed or content extracted --
it just confirms the file was stored and leaves status as "uploaded" so
nothing downstream (content, retrieval) pretends to have real text.
"""
from __future__ import annotations

from app.integrations.interfaces import IngestionResult


class MockIngestionProvider:
    async def ingest(self, book_id: str, file_path: str, file_type: str) -> IngestionResult:
        return IngestionResult(book_id=book_id, status="uploaded", total_pages=None, error=None)
