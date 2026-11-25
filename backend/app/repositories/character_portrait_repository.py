from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.character_portrait import CharacterPortrait


def look(portrait: CharacterPortrait) -> dict | None:
    try:
        value = json.loads(portrait.look_json) if portrait.look_json else None
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def aliases(portrait: CharacterPortrait) -> list[str]:
    try:
        value = json.loads(portrait.aliases_json or "[]")
    except ValueError:
        return []
    return [a for a in value if isinstance(a, str)] if isinstance(value, list) else []


def list_for_book(db: Session, book_id: str) -> list[CharacterPortrait]:
    return list(db.scalars(select(CharacterPortrait).where(CharacterPortrait.book_id == book_id)))


def get(db: Session, book_id: str, char_id: str) -> CharacterPortrait | None:
    return db.get(CharacterPortrait, (book_id, char_id))


def find_by_char_id(db: Session, book_id: str, char_id: str) -> CharacterPortrait | None:
    """The portrait whose primary id OR one of its aliases is `char_id`."""
    portrait = get(db, book_id, char_id)
    if portrait is not None:
        return portrait
    return next((p for p in list_for_book(db, book_id) if char_id in aliases(p)), None)


def create_pending(
    db: Session,
    book_id: str,
    char_id: str,
    *,
    name: str,
    appearance: str | None,
    look: dict | None = None,
    status: str = "pending",
) -> CharacterPortrait:
    """`status="waiting"` records a character with too little description
    to paint yet (no job is queued for it)."""
    portrait = CharacterPortrait(
        book_id=book_id, char_id=char_id, name=name, appearance=appearance, status=status, aliases_json="[]",
        look_json=json.dumps(look) if look else None, upgraded=False,
    )
    db.add(portrait)
    db.commit()
    db.refresh(portrait)
    return portrait


def add_alias(db: Session, portrait: CharacterPortrait, char_id: str) -> None:
    current = aliases(portrait)
    if char_id != portrait.char_id and char_id not in current:
        portrait.aliases_json = json.dumps([*current, char_id])
        db.commit()


def mark_pending(
    db: Session, portrait: CharacterPortrait, *, appearance: str | None, look: dict | None = None
) -> None:
    """Retrying a portrait that never got an image (failed / interrupted).
    Takes the latest appearance since no picture exists yet to stay consistent with."""
    portrait.status = "pending"
    portrait.error = None
    if appearance:
        portrait.appearance = appearance
    if look:
        portrait.look_json = json.dumps(look)
    db.commit()


def update_description(db: Session, portrait: CharacterPortrait, *, appearance: str | None, look: dict | None) -> None:
    """Keeps a waiting portrait's description current (no status change)."""
    if appearance:
        portrait.appearance = appearance
    if look:
        portrait.look_json = json.dumps(look)
    db.commit()


def mark_ready(
    db: Session,
    portrait: CharacterPortrait,
    *,
    image_path: str,
    prompt: str,
    look: dict | None = None,
    placeholder: bool | None = None,
    upgraded: bool | None = None,
) -> None:
    if look:
        portrait.look_json = json.dumps(look)  # the profile the picture was actually painted from
    if placeholder is not None:
        portrait.placeholder = placeholder
    if upgraded is not None:
        portrait.upgraded = upgraded
    portrait.status = "ready"
    portrait.image_path = image_path
    portrait.prompt = prompt
    portrait.error = None
    db.commit()


def mark_failed(
    db: Session, portrait: CharacterPortrait, *, error: str, prompt: str | None = None, status: str = "failed"
) -> None:
    """`status` is "failed" (retried on the next Update) or "skipped" (never retried)."""
    portrait.status = status
    portrait.error = error[:500]
    if prompt is not None:
        portrait.prompt = prompt
    db.commit()


def restore_ready(db: Session, portrait: CharacterPortrait, *, error: str, upgraded: bool) -> None:
    """A placeholder upgrade failed: keep showing the old picture."""
    portrait.status = "ready"
    portrait.error = error[:500]
    portrait.upgraded = upgraded
    db.commit()


def delete_for_book(db: Session, book_id: str) -> None:
    for portrait in list_for_book(db, book_id):
        db.delete(portrait)
    db.commit()
