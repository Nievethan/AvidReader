"""Character portraits: match characters to existing portraits, queue
images for new ones, and attach portrait info to character-map responses.

Rules (see docs/CHARACTER_PORTRAITS_PLAN.md):
- A portrait is generated ONCE per character and reused on every later
  "Update" -- never regenerated or upgraded from later descriptions.
- A character introduced in a later chapter gets a portrait on the next Update.
- Name variants ("Dudley" -> "Dudley Dursley") reuse the same portrait, but
  only when exactly one existing portrait matches; ambiguity -> new portrait.
- Only portraits that never got an image (failed / interrupted) are retried.
- Characters with too little description (fewer than `min_details` concrete
  details and not a main character) are "waiting": no image and no cost, the
  UI shows their initials, and they're painted once the book describes them.
- A portrait painted from too little detail (a main character, or one made
  before these rules) is a placeholder: it is repainted ONCE when a later
  chapter describes the character. Portraits from real descriptions never change.
"""
from __future__ import annotations

import asyncio
import logging
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.orm import Session

from app.db import database
from app.integrations.character_looks import (
    detail_count,
    is_main_role,
    meaningful_appearance,
    merge_looks,
    titled_variant,
)
from app.integrations.interfaces import ReadingBoundary
from app.integrations.portraits import (
    DEFAULT_STYLE,
    CharacterDescriber,
    PortraitGenerator,
    build_portrait_prompt,
    is_nsfw_rejection,
)
from app.models.character_portrait import CharacterPortrait
from app.repositories import character_portrait_repository as repo
from app.schemas.character_map import CharacterNode

logger = logging.getLogger(__name__)

_WORD = re.compile(r"[a-z0-9]+")


def _words(value: str) -> frozenset[str]:
    """Lower-cased name words. Titles count ("mr" vs "mrs"), so Mr. and
    Mrs. Dursley never collapse into one character."""
    return frozenset(_WORD.findall(value.casefold().replace("'s", "")))


def _portrait_word_sets(portrait: CharacterPortrait) -> list[frozenset[str]]:
    sets = [_words(portrait.name)]
    for alias in [portrait.char_id, *repo.aliases(portrait)]:
        sets.append(frozenset(w for w in alias.removeprefix("char_").split("_") if w))
    return [s for s in sets if s]


def _is_name_variant(a: frozenset[str], b: frozenset[str]) -> bool:
    return bool(a) and bool(b) and (a <= b or b <= a)


@dataclass
class PortraitJob:
    book_id: str
    char_id: str  # the portrait's primary char_id
    appearance: str | None
    names: list[str] = field(default_factory=list)
    book_title: str | None = None
    name: str | None = None  # display name: title hints ("Ser", "Lady") + description-pass lookups
    look: dict | None = None  # structured profile from the character map
    setting: str | None = None  # the book's era/place phrase
    boundary: ReadingBoundary | None = None  # reader's position, for the description pass
    upgrade: bool = False  # repainting a placeholder: keep the old picture if this fails


class PortraitService:
    def __init__(
        self,
        *,
        generator: PortraitGenerator,
        portraits_dir: Path,
        concurrency: int = 2,
        describer: CharacterDescriber | None = None,
        style: str = DEFAULT_STYLE,
        min_details: int = 2,
    ) -> None:
        self.generator = generator
        self.style = style
        # Below this many concrete details (and not a main character) a
        # character waits for a description instead of getting a random face.
        self.min_details = max(0, min_details)
        # Optional: one text-model call per new character to describe them from
        # every passage read so far (None = use the character map's profile only).
        self.describer = describer
        self.portraits_dir = Path(portraits_dir)
        self._concurrency = max(1, concurrency)
        self._semaphore: asyncio.Semaphore | None = None
        # (book_id, char_id) of jobs queued or running in this process, so a
        # second Update click doesn't generate the same portrait twice.
        self._active: set[tuple[str, str]] = set()

    # ---- matching -----------------------------------------------------

    def sync(
        self,
        db: Session,
        book_id: str,
        nodes: list[dict],
        *,
        book_title: str | None = None,
        setting: str | None = None,
        boundary: ReadingBoundary | None = None,
    ) -> list[PortraitJob]:
        """Called on every Update, after the graph is saved. Links each
        character to its existing portrait (by id, alias, or unambiguous name
        variant) and returns jobs only for characters that need an image."""
        if not self.generator.available or not nodes:
            return []

        portraits = repo.list_for_book(db, book_id)
        by_id: dict[str, CharacterPortrait] = {}
        for p in portraits:
            by_id[p.char_id] = p
            for alias in repo.aliases(p):
                by_id.setdefault(alias, p)

        claimed: set[str] = set()
        matched: dict[str, CharacterPortrait] = {}

        # 1) exact id / alias matches first, so they can't be stolen by a fuzzy match
        for node in nodes:
            portrait = by_id.get(node["id"])
            if portrait is not None:
                matched[node["id"]] = portrait
                claimed.add(portrait.char_id)

        # 2) unambiguous name variants against portraits not already claimed
        for node in nodes:
            if node["id"] in matched:
                continue
            node_words = _words(node.get("name") or "")
            candidates = [
                p
                for p in portraits
                if p.char_id not in claimed and any(_is_name_variant(node_words, s) for s in _portrait_word_sets(p))
            ]
            if not candidates:
                # Same person under a title ("Magister Illyrio" ~ "Illyrio Mopatis").
                candidates = [
                    p for p in portraits
                    if p.char_id not in claimed
                    and titled_variant(node.get("name") or "", node.get("look"), p.name, repo.look(p))
                ]
            if len(candidates) == 1:
                portrait = candidates[0]
                repo.add_alias(db, portrait, node["id"])
                matched[node["id"]] = portrait
                claimed.add(portrait.char_id)

        names = sorted({n.get("name") or "" for n in nodes} | {p.name for p in portraits})
        jobs: list[PortraitJob] = []
        for node in nodes:
            portrait = matched.get(node["id"])
            appearance = node.get("appearance")
            look = node.get("look") if isinstance(node.get("look"), dict) else None
            described = detail_count(look, appearance) >= self.min_details
            paintable = described or is_main_role(node.get("role"))
            upgrade = False
            if portrait is None:
                portrait = repo.create_pending(
                    db, book_id, node["id"], name=node["name"], appearance=appearance, look=look,
                    status="pending" if paintable else "waiting",
                )
                portraits.append(portrait)
                if not paintable:
                    continue  # no face to draw yet: initials in the UI, no cost
            elif (book_id, portrait.char_id) in self._active:
                continue  # already being generated
            elif portrait.status == "ready":
                # Keep the existing picture -- unless it's a placeholder and the
                # book has now described them: repaint it, once.
                if not (described and self._is_placeholder(portrait) and not portrait.upgraded):
                    continue
                upgrade = True
                repo.mark_pending(db, portrait, appearance=appearance, look=look)
            elif portrait.status == "skipped":
                continue  # the safety filter rejected it twice; retrying won't help
            elif portrait.status == "waiting" and not paintable:
                repo.update_description(db, portrait, appearance=appearance, look=look)
                continue  # still too little to go on
            else:
                # waiting -> now described, failed, or pending from a job that died with the process
                repo.mark_pending(db, portrait, appearance=appearance, look=look)
            key = (book_id, portrait.char_id)
            if key in self._active:
                continue
            self._active.add(key)
            jobs.append(
                PortraitJob(
                    book_id=book_id,
                    char_id=portrait.char_id,
                    appearance=portrait.appearance,
                    names=names,
                    book_title=book_title,
                    name=node.get("name") or portrait.name,
                    look=repo.look(portrait),
                    setting=setting,
                    boundary=boundary,
                    upgrade=upgrade,
                )
            )
        return jobs

    def _is_placeholder(self, portrait: CharacterPortrait) -> bool:
        """Painted from too little detail? Rows made before the flag existed
        are judged from what they were painted from."""
        if portrait.placeholder is not None:
            return bool(portrait.placeholder)
        return detail_count(repo.look(portrait), meaningful_appearance(portrait.appearance)) < max(1, self.min_details)

    # ---- generation ---------------------------------------------------

    async def run_jobs(self, jobs: list[PortraitJob]) -> None:
        """Background task: generates queued portraits, at most
        `concurrency` at a time. Never raises -- a failure marks the portrait
        `failed` and the next Update retries it, except a repeated safety-filter
        rejection, which is marked `skipped` and never retried."""
        if not jobs:
            return
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self._concurrency)
        await asyncio.gather(*(self._run_one(job) for job in jobs))

    async def _run_one(self, job: PortraitJob) -> None:
        key = (job.book_id, job.char_id)
        look = job.look
        prompt = self._prompt(job, look)
        try:
            assert self._semaphore is not None
            async with self._semaphore:
                if self.describer is not None and job.boundary is not None and job.name:
                    # Everything read so far about this character, not just the
                    # batch they first appeared in. Its values win; the map's
                    # profile fills any gaps. None (nothing found / error) -> map only.
                    described = await self.describer.describe(job.book_id, job.name, job.boundary)
                    look = merge_looks(described, job.look)
                    prompt = self._prompt(job, look)
                try:
                    image = await self.generator.generate(prompt)
                except Exception as exc:
                    if not is_nsfw_rejection(exc):
                        raise
                    # Cloudflare's safety filter flags harmless portraits now and
                    # then ("beautiful, golden hair, green eyes"). Retry once,
                    # softened; a second rejection is final (see below).
                    logger.info("Portrait %s/%s flagged as NSFW; retrying softened", job.book_id, job.char_id)
                    prompt = self._prompt(job, look, safe=True)
                    image = await self.generator.generate(prompt)
            path = self._image_path(job.book_id, job.char_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(image)
            with database.SessionLocal() as db:
                portrait = repo.get(db, job.book_id, job.char_id)
                if portrait is not None:  # book may have been deleted meanwhile
                    repo.mark_ready(
                        db, portrait, image_path=str(path), prompt=prompt, look=look,
                        placeholder=detail_count(look, job.appearance) < max(1, self.min_details),
                        upgraded=True if job.upgrade else None,
                    )
        except Exception as exc:
            logger.warning("Portrait generation failed for %s/%s: %s", job.book_id, job.char_id, exc)
            # Rejected by the safety filter even after softening: mark it
            # "skipped" so later Updates stop retrying (the UI keeps the icon).
            # Anything else (rate limit, network) stays "failed" and is retried.
            skipped = is_nsfw_rejection(exc)
            try:
                with database.SessionLocal() as db:
                    portrait = repo.get(db, job.book_id, job.char_id)
                    if portrait is not None and job.upgrade:
                        # The old picture is still on disk: keep showing it. Try the
                        # upgrade again next Update, unless the safety filter refused.
                        repo.restore_ready(db, portrait, error=f"{type(exc).__name__}: {exc}", upgraded=skipped)
                    elif portrait is not None:
                        repo.mark_failed(
                            db, portrait, error=f"{type(exc).__name__}: {exc}", prompt=prompt,
                            status="skipped" if skipped else "failed",
                        )
            except Exception:  # pragma: no cover - defensive
                logger.warning("Could not record portrait failure", exc_info=True)
        finally:
            self._active.discard(key)

    def _prompt(self, job: PortraitJob, look: dict | None, *, safe: bool = False) -> str:
        return build_portrait_prompt(
            job.appearance, names=job.names, book_title=job.book_title, safe=safe,
            look=look, setting=job.setting, name=job.name, style=self.style,
        )

    def _image_path(self, book_id: str, char_id: str) -> Path:
        return self.portraits_dir / book_id / f"{char_id}.jpg"

    # ---- reading ------------------------------------------------------

    def attach(self, db: Session, book_id: str, nodes: list[CharacterNode]) -> list[CharacterNode]:
        """Fills portrait_status / portrait_url on each node from the table."""
        portraits = repo.list_for_book(db, book_id)
        if not portraits:
            return nodes
        by_id: dict[str, CharacterPortrait] = {}
        for p in portraits:
            by_id[p.char_id] = p
            for alias in repo.aliases(p):
                by_id.setdefault(alias, p)
        for node in nodes:
            portrait = by_id.get(node.id)
            if portrait is None:
                continue
            node.portrait_status = portrait.status
            if portrait.status == "ready" and portrait.image_path:
                version = int(portrait.updated_at.timestamp() * 1000) if portrait.updated_at else 0  # ms: a repaint must change the URL
                node.portrait_url = f"/api/v1/books/{book_id}/characters/{node.id}/portrait?v={version}"
        return nodes

    def portrait_file(self, db: Session, book_id: str, char_id: str) -> Path | None:
        portrait = repo.find_by_char_id(db, book_id, char_id)
        if portrait is None or portrait.status != "ready" or not portrait.image_path:
            return None
        path = Path(portrait.image_path)
        return path if path.is_file() else None

    def delete_for_book(self, db: Session, book_id: str) -> None:
        repo.delete_for_book(db, book_id)
        shutil.rmtree(self.portraits_dir / book_id, ignore_errors=True)
