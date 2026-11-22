from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.scene_image import SceneImage


def list_for_book(db: Session, book_id: str) -> list[SceneImage]:
    stmt = select(SceneImage).where(SceneImage.book_id == book_id).order_by(SceneImage.order_index, SceneImage.scene_id)
    return list(db.scalars(stmt))


def get(db: Session, book_id: str, scene_id: str) -> SceneImage | None:
    return db.get(SceneImage, (book_id, scene_id))


def create_pending(
    db: Session,
    book_id: str,
    scene_id: str,
    *,
    order_index: int,
    position: int,
    source_location: str,
    title: str,
    caption: str,
    evidence: str,
    prompt: str,
) -> SceneImage:
    scene = SceneImage(
        book_id=book_id,
        scene_id=scene_id,
        order_index=order_index,
        position=position,
        source_location=source_location,
        title=title,
        caption=caption,
        evidence=evidence,
        prompt=prompt,
        status="pending",
    )
    db.add(scene)
    db.commit()
    db.refresh(scene)
    return scene


def mark_pending(db: Session, scene: SceneImage) -> None:
    scene.status = "pending"
    scene.error = None
    db.commit()


def mark_ready(db: Session, scene: SceneImage, *, image_path: str) -> None:
    scene.status = "ready"
    scene.image_path = image_path
    scene.error = None
    db.commit()


def mark_failed(db: Session, scene: SceneImage, *, error: str) -> None:
    scene.status = "failed"
    scene.error = error[:500]
    db.commit()


def delete_for_book(db: Session, book_id: str) -> None:
    for scene in list_for_book(db, book_id):
        db.delete(scene)
    db.commit()
