"""Grounded AnswerProvider (roadmap Step 8).

Handles all four chat interaction types:
    question, explain    -> answer_type "grounded" (must be cited, else refusal)
    what_if              -> answer_type "hypothetical", built on cited facts
    story_continues      -> answer_type "hypothetical", original continuation

Every model answer is post-processed: invalid [S#] markers are dropped,
quotations not found in the excerpts lose their quote marks, and copied
sentences are removed from story continuations. Model/network failures turn
into a clean "unavailable" answer instead of an error.
"""
from __future__ import annotations

import logging

from app.integrations.cloudflare import CloudflareError
from app.integrations.interfaces import GeneratedAnswer, GenerationRequest, RetrievedPassage
from app.rag.citations import build_citations, check_answer, remove_copied_sentences
from app.rag.llm import ChatModel
from app.rag.prompts import (
    HYPOTHETICAL_TYPES,
    NOT_FOUND_TOKEN,
    REFUSAL_TEXT,
    STORY_TOO_EARLY_TEXT,
    build_messages,
)

logger = logging.getLogger(__name__)

UNAVAILABLE_TEXT = "The AI model is unavailable right now, so I can't answer. Please try again in a moment."
NOT_ORIGINAL_TEXT = "I couldn't write an original continuation this time. Try asking again."


class GroundedAnswerProvider:
    def __init__(self, model: ChatModel, *, max_tokens: int = 400, story_max_tokens: int = 450) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self.story_max_tokens = story_max_tokens

    async def answer(self, request: GenerationRequest, sources: list[RetrievedPassage]) -> GeneratedAnswer:
        kind = request.interaction_type
        hypothetical = kind in HYPOTHETICAL_TYPES

        if not sources:
            return _refusal(STORY_TOO_EARLY_TEXT if kind == "story_continues" else REFUSAL_TEXT)

        max_tokens = self.story_max_tokens if kind == "story_continues" else self.max_tokens
        try:
            raw = await self.model.complete(build_messages(request, sources), max_tokens=max_tokens)
        except CloudflareError as exc:
            logger.warning("Chat model failed: %s", exc)
            return GeneratedAnswer(
                answer=UNAVAILABLE_TEXT,
                answer_type="unavailable",
                is_hypothetical=False,
                provider_status="provider_error",
            )

        if not raw.strip() or NOT_FOUND_TOKEN in raw:
            return _refusal(REFUSAL_TEXT)

        if kind == "story_continues":
            raw, dropped = remove_copied_sentences(raw, sources)
            if dropped:
                logger.info("Removed %d copied sentence(s) from a story continuation", dropped)
            if not raw:
                return _refusal(NOT_ORIGINAL_TEXT)

        checked = check_answer(raw, sources)
        if not checked.cited and not hypothetical:
            # A factual answer with nothing backing it is not shown.
            return _refusal(REFUSAL_TEXT)

        return GeneratedAnswer(
            answer=checked.text,
            answer_type="hypothetical" if hypothetical else "grounded",
            is_hypothetical=hypothetical,
            citations=build_citations(checked.cited, sources),
            provider_status=self.model.status,
        )


def _refusal(text: str) -> GeneratedAnswer:
    return GeneratedAnswer(answer=text, answer_type="refusal", is_hypothetical=False, provider_status="no_evidence")
