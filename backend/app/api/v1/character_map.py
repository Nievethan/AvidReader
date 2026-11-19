from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_book_service, get_character_graph_provider, get_portrait_service
from app.core.errors import NotFoundError
from app.db.database import get_db
from app.integrations.interfaces import CharacterGraphProvider, ReadingBoundary
from app.repositories import book_repository
from app.schemas.character_map import RelationshipsResponse
from app.services.book_service import BookService
from app.services.character_map_service import CharacterMapService
from app.services.portrait_service import PortraitService

router = APIRouter(prefix="/books/{book_id}/relationships", tags=["character-map"])
portrait_router = APIRouter(prefix="/books/{book_id}/characters", tags=["character-map"])


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
    portrait_service: PortraitService = Depends(get_portrait_service),
) -> RelationshipsResponse:
    """Whatever's cached from the last "Update" -- free, no model call.
    `not_available` if nothing has been generated yet. Portrait status is
    read fresh from the portraits table, so polling this shows progress."""
    book_service.get_book_or_404(db, book_id)
    response = CharacterMapService().get_cached(db, book_id)
    portrait_service.attach(db, book_id, response.nodes)
    return response


@router.post("/generate", response_model=RelationshipsResponse)
async def generate_relationships(
    book_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    book_service: BookService = Depends(get_book_service),
    provider: CharacterGraphProvider = Depends(get_character_graph_provider),
    portrait_service: PortraitService = Depends(get_portrait_service),
) -> RelationshipsResponse:
    """The "Update" button: extracts fresh from everything read so far and
    replaces the cache. Costs a real model call -- not triggered by GET.
    Characters without a portrait get one generated in the background;
    existing portraits are always reused."""
    book = book_service.get_book_or_404(db, book_id)
    boundary, label = _resolve_boundary(db, book)
    response = await CharacterMapService().generate(db, book_id, boundary, boundary_label=label, provider=provider)
    if response.status == "ready":
        jobs = portrait_service.sync(
            db, book_id, [node.model_dump() for node in response.nodes], book_title=book.title
        )
        portrait_service.attach(db, book_id, response.nodes)
        if jobs:
            background_tasks.add_task(portrait_service.run_jobs, jobs)
    return response


@portrait_router.get("/{char_id}/portrait", response_class=FileResponse)
def get_portrait(
    book_id: str,
    char_id: str,
    db: Session = Depends(get_db),
    book_service: BookService = Depends(get_book_service),
    portrait_service: PortraitService = Depends(get_portrait_service),
) -> FileResponse:
    """The character's portrait JPEG (also resolves name-variant aliases).
    404 while it's still being generated or if it never was. The URL carries
    a version query, so the image can be cached long-term."""
    book_service.get_book_or_404(db, book_id)
    path = portrait_service.portrait_file(db, book_id, char_id)
    if path is None:
        raise NotFoundError("No portrait for this character yet.")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=31536000"})
