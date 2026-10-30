"""Placeholder AnswerProvider used until Gitae's real generation exists.

Rules this mock must never break:
- citations are always [] (no retrieval happened, so no real source exists)
- creative interaction types are always labeled hypothetical
- the answer text is always prefixed so nobody mistakes it for a real answer
"""
from __future__ import annotations

from app.integrations.interfaces import GeneratedAnswer, GenerationRequest, RetrievedPassage

CREATIVE_INTERACTION_TYPES = {"what_if", "story_continues"}


class MockAnswerProvider:
    async def answer(
        self, request: GenerationRequest, sources: list[RetrievedPassage]
    ) -> GeneratedAnswer:
        is_hypothetical = request.interaction_type in CREATIVE_INTERACTION_TYPES
        answer_type = "hypothetical" if is_hypothetical else "mock"

        answer = (
            f"[MOCK RESPONSE] Real AI/RAG is not connected yet. "
            f"Received question for book {request.book_id} in '{request.mode}' mode "
            f"(interaction: {request.interaction_type}). No real retrieval or generation occurred."
        )

        return GeneratedAnswer(
            answer=answer,
            answer_type=answer_type,
            is_hypothetical=is_hypothetical,
            citations=[],
        )
