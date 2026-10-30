from __future__ import annotations

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
