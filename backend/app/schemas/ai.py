from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Mode = Literal["study", "research", "creative"]
InteractionType = Literal["question", "explain", "what_if", "story_continues"]
ExplanationLevel = Literal["simple", "standard", "advanced"]


class ReadingPositionSchema(BaseModel):
    current_page: int | None = None
    current_chapter: int | None = None
    location: str | None = None


class ChatRequest(BaseModel):
    book_id: str
    conversation_id: str | None = None
    question: str = Field(min_length=1, max_length=4000)
    mode: Mode = "research"
    interaction_type: InteractionType = "question"
    reading_position: ReadingPositionSchema | None = None
    selected_passage: str | None = None
    explanation_level: ExplanationLevel = "standard"


class SpoilerScope(BaseModel):
    restricted_to_progress: bool
    reason: str


class ChatResponse(BaseModel):
    conversation_id: str
    message_id: str
    book_id: str
    answer: str
    answer_type: str
    provider_status: str
    is_hypothetical: bool
    citations: list[dict]
    spoiler_scope: SpoilerScope
    created_at: datetime


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    answer_type: str | None = None
    is_hypothetical: bool
    citations: list[dict]
    created_at: datetime


class ConversationResponse(BaseModel):
    id: str
    book_id: str
    created_at: datetime
    messages: list[MessageResponse]
