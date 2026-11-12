from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.integrations.interfaces import GraphResult
from app.models.character_graph import CharacterGraphCache


def get_cached(db: Session, book_id: str) -> CharacterGraphCache | None:
    return db.get(CharacterGraphCache, book_id)


def save(db: Session, book_id: str, result: GraphResult, *, boundary_label: str | None) -> CharacterGraphCache:
    cache = db.get(CharacterGraphCache, book_id)
    nodes_json = json.dumps(result.nodes)
    edges_json = json.dumps(result.edges)
    if cache is None:
        cache = CharacterGraphCache(
            book_id=book_id, nodes_json=nodes_json, edges_json=edges_json, boundary_label=boundary_label
        )
        db.add(cache)
    else:
        cache.nodes_json = nodes_json
        cache.edges_json = edges_json
        cache.boundary_label = boundary_label
    db.commit()
    db.refresh(cache)
    return cache


def delete_for_book(db: Session, book_id: str) -> None:
    cache = db.get(CharacterGraphCache, book_id)
    if cache is not None:
        db.delete(cache)
        db.commit()
