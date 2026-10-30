from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.integrations.interfaces import AnswerProvider, GenerationRequest, ReadingBoundary
from app.models.ai import Conversation, Message
from app.repositories import ai_repository, book_repository
from app.schemas.ai import ChatRequest


class AIService:
    def __init__(self, answer_provider: AnswerProvider):
        self.answer_provider = answer_provider

    def _get_or_create_conversation(self, db: Session, request: ChatRequest) -> Conversation:
        if request.conversation_id:
            conversation = ai_repository.get_conversation(db, request.conversation_id)
            if conversation is None or conversation.book_id != request.book_id:
                raise NotFoundError(
                    f"Conversation {request.conversation_id} was not found for book {request.book_id}."
                )
            return conversation
        return ai_repository.create_conversation(db, request.book_id)

    async def chat(self, db: Session, request: ChatRequest) -> Message:
        book = book_repository.get_book(db, request.book_id)
        if book is None:
            raise NotFoundError(f"Book {request.book_id} was not found.")

        conversation = self._get_or_create_conversation(db, request)

        position = request.reading_position
        boundary = ReadingBoundary(
            book_id=request.book_id,
            current_page=position.current_page if position else None,
            current_chapter=position.current_chapter if position else None,
            location=position.location if position else None,
        )

        ai_repository.add_message(db, conversation.id, role="user", content=request.question)

        generation_request = GenerationRequest(
            book_id=request.book_id,
            question=request.question,
            mode=request.mode,
            interaction_type=request.interaction_type,
            reading_boundary=boundary,
            selected_passage=request.selected_passage,
            explanation_level=request.explanation_level,
        )

        # No RetrievalProvider is wired in yet (Umer's work) -- sources
        # stay empty so the mock provider never fabricates citations.
        generated = await self.answer_provider.answer(generation_request, sources=[])

        assistant_message = ai_repository.add_message(
            db,
            conversation.id,
            role="assistant",
            content=generated.answer,
            answer_type=generated.answer_type,
            provider_status="mock",
            is_hypothetical=generated.is_hypothetical,
        )
        assistant_message.citations = generated.citations
        db.add(assistant_message)
        db.commit()
        db.refresh(assistant_message)
        return assistant_message
