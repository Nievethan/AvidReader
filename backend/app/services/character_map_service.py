from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.integrations.interfaces import CharacterGraphProvider, ReadingBoundary
from app.repositories import character_graph_repository
from app.schemas.character_map import CharacterEdge, CharacterNode, RelationshipsResponse

_NOT_GENERATED_MESSAGE = "Nothing generated yet -- tap Update to extract characters from what you've read so far."
_FALLBACK_ERROR_MESSAGE = "Couldn't build the character map. Tap Update to try again."


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
            setting=cache.setting,
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
        """Extends the saved map with the text read since the last Update
        (the provider decides what's new and batches it to fit the model)."""
        cache = character_graph_repository.get_cached(db, book_id)
        previous = character_graph_repository.to_graph_result(cache) if cache is not None else None
        result = await provider.get_graph(book_id, boundary, previous=previous)

        if result.status != "ready":
            message = result.message or _FALLBACK_ERROR_MESSAGE
            if cache is not None:
                # Keep showing the map we already have; just explain what happened.
                response = self.get_cached(db, book_id)
                response.message = message
                return response
            return RelationshipsResponse(book_id=book_id, status="not_available", source=result.source, message=message)

        # When this Update stopped early, label the map with where it got to,
        # not with the reader's position.
        label = boundary_label
        if not result.complete:
            label = result.processed_through_label or (cache.boundary_label if cache is not None else None)
        cache = character_graph_repository.save(db, book_id, result, boundary_label=label)
        return RelationshipsResponse(
            book_id=book_id,
            status="ready",
            source=result.source,
            message=result.message,
            nodes=[CharacterNode(**n) for n in result.nodes],
            edges=[CharacterEdge(**e) for e in result.edges],
            generated_at=cache.generated_at,
            boundary_label=label,
            setting=cache.setting,
        )
