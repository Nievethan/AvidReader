from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_book_service, get_character_graph_provider
from app.db.database import get_db
from app.integrations.interfaces import CharacterGraphProvider, ReadingBoundary
from app.repositories import book_repository
from app.schemas.character_map import RelationshipsResponse
from app.services.book_service import BookService
from app.services.character_map_service import CharacterMapService

router = APIRouter(prefix="/books/{book_id}/relationships", tags=["character-map"])


def _resolve_boundary(db: Session, book) -> tuple[ReadingBoundary, str | None]:
    unit_field = "current_page" if book.file_type == "pdf" else "current_chapter"
    unit_name = "page" if unit_field == "current_page" else "chapter"
    progress = book_repository.get_progress(db, book.id)
    limit = getattr(progress, unit_field, None) if progress else None
    boundary = ReadingBoundary(
        book_id=book.id,
        current_page=progress.current_page if progress else None,
        current_chapter=progress.current_chapter if progress else None,
        max_position=limit,
    )
    label = f"{unit_name} {limit}" if limit is not None else None
    return boundary, label


@router.get("", response_model=RelationshipsResponse)
def get_relationships(
    book_id: str,
    db: Session = Depends(get_db),
    book_service: BookService = Depends(get_book_service),
) -> RelationshipsResponse:
    """Whatever's cached from the last "Update" -- free, no model call.
    `not_available` if nothing has been generated yet."""
    book_service.get_book_or_404(db, book_id)
    return CharacterMapService().get_cached(db, book_id)


@router.post("/generate", response_model=RelationshipsResponse)
async def generate_relationships(
    book_id: str,
    db: Session = Depends(get_db),
    book_service: BookService = Depends(get_book_service),
    provider: CharacterGraphProvider = Depends(get_character_graph_provider),
) -> RelationshipsResponse:
    """The "Update" button: extracts fresh from everything read so far and
    replaces the cache. Costs a real model call -- not triggered by GET."""
    book = book_service.get_book_or_404(db, book_id)
    boundary, label = _resolve_boundary(db, book)
    return await CharacterMapService().generate(db, book_id, boundary, boundary_label=label, provider=provider)
