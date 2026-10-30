from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    book_id: Mapped[str] = mapped_column(String(36), ForeignKey("books.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    conversation_id: Mapped[str] = mapped_column(String(36), ForeignKey("conversations.id"))
    role: Mapped[str] = mapped_column(String(10))  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text)

    # Assistant-only fields; null for user messages.
    answer_type: Mapped[str | None] = mapped_column(String(20), nullable=True)  # mock | hypothetical | grounded
    provider_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_hypothetical: Mapped[bool] = mapped_column(Boolean, default=False)
    citations_json: Mapped[str] = mapped_column(Text, default="[]")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")

    @property
    def citations(self) -> list[dict]:
        return json.loads(self.citations_json)

    @citations.setter
    def citations(self, value: list[dict]) -> None:
        self.citations_json = json.dumps(value)
