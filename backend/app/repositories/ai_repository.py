from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.ai import Conversation, Message


def create_conversation(db: Session, book_id: str) -> Conversation:
    conversation = Conversation(book_id=book_id)
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def get_conversation(db: Session, conversation_id: str) -> Conversation | None:
    return db.get(Conversation, conversation_id)


def add_message(db: Session, conversation_id: str, **fields) -> Message:
    message = Message(conversation_id=conversation_id, **fields)
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def count_user_messages(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(Message).where(Message.role == "user")) or 0


def delete_for_book(db: Session, book_id: str) -> None:
    """Removes a deleted book's conversations (and their messages, via the
    model's cascade) -- otherwise they linger as orphaned rows forever."""
    for conversation in db.scalars(select(Conversation).where(Conversation.book_id == book_id)):
        db.delete(conversation)
    db.commit()
