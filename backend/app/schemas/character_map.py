from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CharacterNode(BaseModel):
    id: str
    name: str
    role: str | None = None
    description: str | None = None
    first_seen_chunk_id: str | None = None
    # Visual description extracted from the text read so far (no names).
    appearance: str | None = None
    # Structured look profile (sex, age, hair, clothing...) -- see character_looks.py.
    look: dict | None = None
    # Filled from the character_portraits table at response time.
    portrait_status: str = "none"  # "none" | "pending" | "ready" | "failed" | "skipped" | "waiting"
    portrait_url: str | None = None


class CharacterEdge(BaseModel):
    id: str
    source: str
    target: str
    relationship: str | None = None
    label: str | None = None
    evidence: str | None = None


class RelationshipsResponse(BaseModel):
    book_id: str
    status: str  # "not_available" | "ready"
    source: str = "none"  # "none" | "fixture" | "extracted"
    message: str | None = None
    nodes: list[CharacterNode] = Field(default_factory=list)
    edges: list[CharacterEdge] = Field(default_factory=list)
    generated_at: datetime | None = None
    boundary_label: str | None = None
    # Name-free era/place phrase used in portrait prompts.
    setting: str | None = None
