from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.integrations.interfaces import CharacterGraphProvider, ReadingBoundary
from app.repositories import character_graph_repository
from app.schemas.character_map import CharacterEdge, CharacterNode, RelationshipsResponse

_NOT_AVAILABLE_MESSAGE = "Character extraction isn't connected yet (Gitae's work)."
_NOT_GENERATED_MESSAGE = "Nothing generated yet -- tap Update to extract characters from what you've read so far."


class CharacterMapService:
    def get_cached(self, db: Session, book_id: str) -> RelationshipsResponse:
        cache = character_graph_repository.get_cached(db, book_id)
        if cache is None:
            return RelationshipsResponse(
                book_id=book_id, status="not_available", source="none", message=_NOT_GENERATED_MESSAGE
            )
        return RelationshipsResponse(
            book_id=book_id,
            status="ready",
            source="extracted",
            nodes=[CharacterNode(**n) for n in json.loads(cache.nodes_json)],
            edges=[CharacterEdge(**e) for e in json.loads(cache.edges_json)],
            generated_at=cache.generated_at,
            boundary_label=cache.boundary_label,
        )

    async def generate(
        self,
        db: Session,
        book_id: str,
        boundary: ReadingBoundary,
        *,
        boundary_label: str | None,
        provider: CharacterGraphProvider,
    ) -> RelationshipsResponse:
        result = await provider.get_graph(book_id, boundary)
        if result.status != "ready":
            return RelationshipsResponse(
                book_id=book_id, status="not_available", source=result.source, message=_NOT_AVAILABLE_MESSAGE
            )
        cache = character_graph_repository.save(db, book_id, result, boundary_label=boundary_label)
        return RelationshipsResponse(
            book_id=book_id,
            status="ready",
            source=result.source,
            nodes=[CharacterNode(**n) for n in result.nodes],
            edges=[CharacterEdge(**e) for e in result.edges],
            generated_at=cache.generated_at,
            boundary_label=boundary_label,
        )
