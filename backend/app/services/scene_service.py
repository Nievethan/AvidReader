"""Scene pictures: the reader taps "Illustrate" on a page (PDF) or chapter
(EPUB) and gets a storybook-style picture of its key moment.

Flow of one tap (POST /books/{id}/scenes/at/{position}):
1. Spoiler gate: the position must be one the reader has reached.
2. Already illustrated -> the saved picture comes straight back (no model
   call). Failed before -> repainted from the saved prompt.
3. Otherwise the chat model picks the page's key moment (grounded by an
   exact quote, see app/integrations/scenes.py), the image model paints it,
   and the result is saved and returned -- all within the request.

The Scenes gallery (GET /books/{id}/scenes) lists every illustrated position
the reader has reached. Moving backwards hides later scenes; it doesn't
delete them.
"""
from __future__ import annotations

import asyncio
import json
import logging
import shutil
from pathlib import Path

from sqlalchemy.orm import Session

from app.integrations.character_graph import split_into_batches
from app.integrations.interfaces import ReadingBoundary, RetrievalProvider, RetrievedPassage
from app.integrations.portraits import PortraitGenerator
from app.integrations.scenes import ScenePicker, build_scene_prompt
from app.models.scene_image import SceneImage
from app.repositories import character_graph_repository
from app.repositories import scene_repository as repo
from app.schemas.scenes import SceneItem, SceneResult, ScenesResponse

logger = logging.getLogger(__name__)

OFFLINE_MESSAGE = "Scene pictures need an AI model. Add Cloudflare credentials to backend/.env and restart the backend."
NO_SCENES_MESSAGE = "No scenes yet -- tap Illustrate while reading to picture the page you're on."
NOT_REACHED_MESSAGE = "You haven't reached that part of the book yet."
EMPTY_PAGE_MESSAGE = "There's no text on this {unit} to illustrate (it may be blank or still processing)."
NO_MOMENT_MESSAGE = "Couldn't find a moment to draw on this {unit}. Tap Illustrate to try again."
PICK_ERROR_MESSAGE = "The AI service returned an error while reading this {unit}. Tap Illustrate to try again."
PAINT_ERROR_MESSAGE = "The picture couldn't be painted (the image service returned an error). Tap Illustrate to try again."


def scene_id_for(position: int) -> str:
    return f"p{position:05d}"


def _covers(passage: RetrievedPassage, position: int) -> bool:
    if passage.page_start is not None:
        return passage.page_start <= position <= (passage.page_end or passage.page_start)
    return passage.chapter == position


class SceneService:
    def __init__(
        self,
        *,
        picker: ScenePicker,
        generator: PortraitGenerator,
        retrieval_provider: RetrievalProvider | None,
        scenes_dir: Path,
        max_page_chars: int = 60_000,
    ) -> None:
        self.picker = picker
        self.generator = generator
        self.retrieval_provider = retrieval_provider
        self.scenes_dir = Path(scenes_dir)
        self.max_page_chars = max_page_chars
        # One in-flight illustration per (book, position): a double tap
        # waits for the first and then gets its saved picture back.
        self._locks: dict[tuple[str, int], asyncio.Lock] = {}

    @property
    def available(self) -> bool:
        return self.picker.available and self.generator.available and self.retrieval_provider is not None

    # ---- reading (free, no model call) ---------------------------------

    @staticmethod
    def is_visible(scene: SceneImage, boundary: ReadingBoundary) -> bool:
        limit = boundary.limit
        return limit is not None and scene.position <= limit

    def list_visible(self, db: Session, book_id: str, boundary: ReadingBoundary) -> ScenesResponse:
        scenes = [s for s in repo.list_for_book(db, book_id) if self.is_visible(s, boundary)]
        message = None
        if not scenes:
            message = NO_SCENES_MESSAGE if self.available else OFFLINE_MESSAGE
        return ScenesResponse(
            book_id=book_id,
            status="ready" if scenes else "not_available",
            message=message,
            scenes=[self.to_item(s) for s in scenes],
        )

    @staticmethod
    def to_item(scene: SceneImage) -> SceneItem:
        url = None
        if scene.status == "ready" and scene.image_path:
            version = int(scene.updated_at.timestamp()) if scene.updated_at else 0
            url = f"/api/v1/books/{scene.book_id}/scenes/{scene.scene_id}/image?v={version}"
        return SceneItem(
            id=scene.scene_id,
            title=scene.title,
            caption=scene.caption,
            source_location=scene.source_location,
            position=scene.position,
            status=scene.status,
            image_url=url,
        )

    def image_file(self, db: Session, book_id: str, scene_id: str, boundary: ReadingBoundary) -> Path | None:
        scene = repo.get(db, book_id, scene_id)
        if scene is None or not self.is_visible(scene, boundary):
            return None
        if scene.status != "ready" or not scene.image_path:
            return None
        path = Path(scene.image_path)
        return path if path.is_file() else None

    # ---- the Illustrate button -----------------------------------------

    async def illustrate(
        self,
        db: Session,
        book_id: str,
        position: int,
        boundary: ReadingBoundary,
        *,
        unit: str,
        book_title: str | None = None,
    ) -> SceneResult:
        """`unit` is "page" or "chapter" (for labels and messages)."""
        if not self.available:
            return SceneResult(book_id=book_id, status="not_available", message=OFFLINE_MESSAGE)
        limit = boundary.limit
        if limit is None or position < 1 or position > limit:
            return SceneResult(book_id=book_id, status="not_available", message=NOT_REACHED_MESSAGE)

        lock = self._locks.setdefault((book_id, position), asyncio.Lock())
        async with lock:
            scene_id = scene_id_for(position)
            scene = repo.get(db, book_id, scene_id)
            if scene is not None and scene.status == "ready":
                return SceneResult(book_id=book_id, status="ready", scene=self.to_item(scene))
            if scene is None:
                scene_or_message = await self._pick(db, book_id, position, unit=unit, book_title=book_title)
                if isinstance(scene_or_message, str):
                    return SceneResult(book_id=book_id, status="not_available", message=scene_or_message)
                scene = scene_or_message
            else:
                repo.mark_pending(db, scene)  # failed (or interrupted) earlier: repaint from the saved prompt
            return await self._paint(db, scene)

    async def _pick(
        self, db: Session, book_id: str, position: int, *, unit: str, book_title: str | None
    ) -> SceneImage | str:
        assert self.retrieval_provider is not None
        page_boundary = ReadingBoundary(book_id=book_id, max_position=position)
        passages = await self.retrieval_provider.list_chunks(book_id, page_boundary)
        on_page = sorted((p for p in passages if _covers(p, position)), key=lambda p: p.order_index)
        if not on_page:
            return EMPTY_PAGE_MESSAGE.format(unit=unit)
        # A long EPUB chapter is cut to what fits the model's context.
        on_page = split_into_batches(on_page, self.max_page_chars)[0]
        try:
            picked = await self.picker.pick(on_page, 1)
        except Exception:
            logger.warning("Scene picking failed for book %s %s %s", book_id, unit, position, exc_info=True)
            return PICK_ERROR_MESSAGE.format(unit=unit)
        if not picked:
            return NO_MOMENT_MESSAGE.format(unit=unit)
        moment = picked[0]
        names = [*self._character_names(db, book_id), *moment.names]
        return repo.create_pending(
            db,
            book_id,
            scene_id_for(position),
            order_index=moment.passage.order_index,
            position=position,
            source_location=f"{unit} {position}",
            title=moment.title,
            caption=moment.caption,
            evidence=moment.evidence,
            prompt=build_scene_prompt(moment.visual, names=names, book_title=book_title),
        )

    async def _paint(self, db: Session, scene: SceneImage) -> SceneResult:
        try:
            image = await self.generator.generate(scene.prompt)
            path = self.scenes_dir / scene.book_id / f"{scene.scene_id}.jpg"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(image)
            repo.mark_ready(db, scene, image_path=str(path))
        except Exception as exc:
            logger.warning("Scene image failed for %s/%s: %s", scene.book_id, scene.scene_id, exc)
            repo.mark_failed(db, scene, error=f"{type(exc).__name__}: {exc}")
            return SceneResult(
                book_id=scene.book_id, status="failed", message=PAINT_ERROR_MESSAGE, scene=self.to_item(scene)
            )
        return SceneResult(book_id=scene.book_id, status="ready", scene=self.to_item(scene))

    @staticmethod
    def _character_names(db: Session, book_id: str) -> list[str]:
        """Names from the character map (if one was built). Together with the
        proper nouns of the page, they're scrubbed from image prompts as a
        safety net -- the model is told not to use names at all."""
        cache = character_graph_repository.get_cached(db, book_id)
        if cache is None:
            return []
        try:
            nodes = json.loads(cache.nodes_json)
        except ValueError:
            return []
        return sorted({n.get("name") or "" for n in nodes if isinstance(n, dict)} - {""})

    def delete_for_book(self, db: Session, book_id: str) -> None:
        repo.delete_for_book(db, book_id)
        shutil.rmtree(self.scenes_dir / book_id, ignore_errors=True)
