from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_ai_service
from app.core.errors import NotFoundError
from app.db.database import get_db
from app.repositories import ai_repository
from app.schemas.ai import (
    ChatRequest,
    ChatResponse,
    ConversationResponse,
    MessageResponse,
    SpoilerScope,
)
from app.services.ai_service import AIService

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    db: Session = Depends(get_db),
    service: AIService = Depends(get_ai_service),
) -> ChatResponse:
    assistant_message = await service.chat(db, request)
    return ChatResponse(
        conversation_id=assistant_message.conversation_id,
        message_id=assistant_message.id,
        book_id=request.book_id,
        answer=assistant_message.content,
        answer_type=assistant_message.answer_type or "mock",
        provider_status=assistant_message.provider_status or "mock",
        is_hypothetical=assistant_message.is_hypothetical,
        citations=assistant_message.citations,
        spoiler_scope=SpoilerScope(
            restricted_to_progress=False,
            reason="RAG retrieval provider is not connected yet; no spoiler boundary is enforced.",
        ),
        created_at=assistant_message.created_at,
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
def get_conversation(conversation_id: str, db: Session = Depends(get_db)) -> ConversationResponse:
    conversation = ai_repository.get_conversation(db, conversation_id)
    if conversation is None:
        raise NotFoundError(f"Conversation {conversation_id} was not found.")
    return ConversationResponse(
        id=conversation.id,
        book_id=conversation.book_id,
        created_at=conversation.created_at,
        messages=[
            MessageResponse(
                id=m.id,
                role=m.role,
                content=m.content,
                answer_type=m.answer_type,
                is_hypothetical=m.is_hypothetical,
                citations=m.citations,
                created_at=m.created_at,
            )
            for m in conversation.messages
        ],
    )
