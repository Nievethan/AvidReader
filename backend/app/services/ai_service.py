from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.integrations.interfaces import (
    AnswerProvider,
    GeneratedAnswer,
    GenerationRequest,
    ReadingBoundary,
    RetrievalProvider,
    RetrievedPassage,
)
from app.models.ai import Conversation, Message
from app.models.books import Book
from app.repositories import ai_repository, book_repository
from app.schemas.ai import ChatRequest

NOT_READY_ANSWERS = {
    "uploaded": "This book hasn't been processed yet, so I can't answer questions about it.",
    "processing": "This book is still being processed. Ask again once it's ready.",
    "failed": "Processing failed for this book, so I can't answer questions about it. Try re-uploading it.",
    "unsupported": "This file has no extractable text (for example a scanned PDF), so I can't answer questions about it.",
}


@dataclass(frozen=True)
class SpoilerInfo:
    restricted: bool
    reason: str


@dataclass(frozen=True)
class ChatOutcome:
    message: Message
    spoiler: SpoilerInfo


class AIService:
    def __init__(
        self,
        answer_provider: AnswerProvider,
        retrieval_provider: RetrievalProvider | None = None,
        *,
        history_max_messages: int = 6,
        story_context_chunks: int = 3,
    ):
        self.answer_provider = answer_provider
        self.retrieval_provider = retrieval_provider
        self.history_max_messages = history_max_messages
        self.story_context_chunks = story_context_chunks

    def _get_or_create_conversation(self, db: Session, request: ChatRequest) -> Conversation:
        if request.conversation_id:
            conversation = ai_repository.get_conversation(db, request.conversation_id)
            if conversation is None or conversation.book_id != request.book_id:
                raise NotFoundError(
                    f"Conversation {request.conversation_id} was not found for book {request.book_id}."
                )
            return conversation
        return ai_repository.create_conversation(db, request.book_id)

    @staticmethod
    def resolve_boundary(db: Session, book: Book, request: ChatRequest) -> tuple[ReadingBoundary, SpoilerInfo]:
        """Spoiler limit in the book's own unit: page for PDF, chapter for
        EPUB. Order: position sent with the request -> saved reading progress
        -> no limit."""
        unit_field = "current_page" if book.file_type == "pdf" else "current_chapter"
        unit_name = "page" if unit_field == "current_page" else "chapter"
        position = request.reading_position

        limit, source = None, None
        if position is not None and getattr(position, unit_field) is not None:
            limit, source = getattr(position, unit_field), "your current position"
        else:
            progress = book_repository.get_progress(db, book.id)
            if progress is not None and getattr(progress, unit_field) is not None:
                limit, source = getattr(progress, unit_field), "your saved reading progress"

        boundary = ReadingBoundary(
            book_id=book.id,
            current_page=position.current_page if position else None,
            current_chapter=position.current_chapter if position else None,
            location=position.location if position else None,
            max_position=limit,
        )
        if limit is None:
            return boundary, SpoilerInfo(False, "No reading position is known, so the whole book was searched.")
        return boundary, SpoilerInfo(True, f"Limited to {unit_name} {limit} ({source}).")

    async def _gather_sources(self, request: ChatRequest, boundary: ReadingBoundary) -> list[RetrievedPassage]:
        retrieval = self.retrieval_provider
        if retrieval is None:
            return []
        if request.interaction_type == "story_continues":
            # No query to search for: continue from the text just before the reader.
            return await retrieval.list_chunks(request.book_id, boundary, last_n=self.story_context_chunks)
        query = request.question
        if request.interaction_type == "explain" and request.selected_passage:
            query = request.selected_passage
        return await retrieval.retrieve(request.book_id, query, boundary)

    def _history(self, conversation: Conversation) -> list[dict]:
        if self.history_max_messages <= 0:
            return []
        recent = conversation.messages[-self.history_max_messages :]
        return [{"role": m.role, "content": m.content} for m in recent]

    async def chat(self, db: Session, request: ChatRequest) -> ChatOutcome:
        book = book_repository.get_book(db, request.book_id)
        if book is None:
            raise NotFoundError(f"Book {request.book_id} was not found.")

        conversation = self._get_or_create_conversation(db, request)
        boundary, spoiler = self.resolve_boundary(db, book, request)
        history = self._history(conversation)

        ai_repository.add_message(db, conversation.id, role="user", content=request.question)

        if self.retrieval_provider is not None and book.processing_status != "ready":
            generated = GeneratedAnswer(
                answer=NOT_READY_ANSWERS.get(book.processing_status, NOT_READY_ANSWERS["uploaded"]),
                answer_type="unavailable",
                is_hypothetical=False,
                provider_status="book_not_ready",
            )
        else:
            generation_request = GenerationRequest(
                book_id=request.book_id,
                question=request.question,
                mode=request.mode,
                interaction_type=request.interaction_type,
                reading_boundary=boundary,
                selected_passage=request.selected_passage,
                explanation_level=request.explanation_level,
                conversation_history=history,
            )
            sources = await self._gather_sources(request, boundary)
            generated = await self.answer_provider.answer(generation_request, sources=sources)

        assistant_message = ai_repository.add_message(
            db,
            conversation.id,
            role="assistant",
            content=generated.answer,
            answer_type=generated.answer_type,
            provider_status=generated.provider_status,
            is_hypothetical=generated.is_hypothetical,
        )
        assistant_message.citations = generated.citations
        db.add(assistant_message)
        db.commit()
        db.refresh(assistant_message)
        return ChatOutcome(message=assistant_message, spoiler=spoiler)
