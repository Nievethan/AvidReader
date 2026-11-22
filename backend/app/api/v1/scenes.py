from __future__ import annotations

from fastapi import APIRouter, Depends, Path as PathParam
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_book_service, get_scene_service
from app.core.errors import NotFoundError
from app.db.database import get_db
from app.integrations.interfaces import ReadingBoundary
from app.repositories import book_repository
from app.schemas.scenes import SceneResult, ScenesResponse
from app.services.book_service import BookService
from app.services.scene_service import SceneService

router = APIRouter(prefix="/books/{book_id}/scenes", tags=["scenes"])


def scene_boundary(db: Session, book) -> tuple[ReadingBoundary, str]:
    """How far the reader has got, as a 1-based page (PDF) or chapter (EPUB).

    The Flutter reader saves `current_page` 0-based ("p. 0" is the first
    page) while ingested text and /content number pages from 1, so a PDF's
    saved page is shifted by one here. EPUB chapters are 1-based already."""
    progress = book_repository.get_progress(db, book.id)
    if book.file_type == "pdf":
        unit = "page"
        saved = progress.current_page if progress else None
        limit = saved + 1 if saved is not None else None
    else:
        unit = "chapter"
        limit = progress.current_chapter if progress else None
    return ReadingBoundary(book_id=book.id, max_position=limit), unit


@router.get("", response_model=ScenesResponse)
def get_scenes(
    book_id: str,
    db: Session = Depends(get_db),
    book_service: BookService = Depends(get_book_service),
    scene_service: SceneService = Depends(get_scene_service),
) -> ScenesResponse:
    """The Scenes gallery: every illustrated page/chapter the reader has
    already reached, in reading order. Free, no model call."""
    book = book_service.get_book_or_404(db, book_id)
    boundary, _ = scene_boundary(db, book)
    return scene_service.list_visible(db, book_id, boundary)


@router.post("/at/{position}", response_model=SceneResult)
async def illustrate_position(
    book_id: str,
    position: int = PathParam(ge=1, description="1-based page (PDF) or chapter (EPUB)"),
    db: Session = Depends(get_db),
    book_service: BookService = Depends(get_book_service),
    scene_service: SceneService = Depends(get_scene_service),
) -> SceneResult:
    """The reader's Illustrate button. Returns the saved picture if this
    page/chapter was illustrated before; otherwise picks its key moment and
    paints it (a real model call -- takes a few seconds)."""
    book = book_service.get_book_or_404(db, book_id)
    boundary, unit = scene_boundary(db, book)
    return await scene_service.illustrate(db, book_id, position, boundary, unit=unit, book_title=book.title)


@router.get("/{scene_id}/image", response_class=FileResponse)
def get_scene_image(
    book_id: str,
    scene_id: str,
    db: Session = Depends(get_db),
    book_service: BookService = Depends(get_book_service),
    scene_service: SceneService = Depends(get_scene_service),
) -> FileResponse:
    """The scene's JPEG. 404 if it isn't painted or the reader hasn't
    reached that part of the book (spoiler gate)."""
    book = book_service.get_book_or_404(db, book_id)
    boundary, _ = scene_boundary(db, book)
    path = scene_service.image_file(db, book_id, scene_id, boundary)
    if path is None:
        raise NotFoundError("No picture for this scene yet.")
    # Short cache: the gate can close again if the reader moves backwards.
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=300"})
