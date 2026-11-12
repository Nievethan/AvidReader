from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CharacterNode(BaseModel):
    id: str
    name: str
    role: str | None = None
    description: str | None = None
    first_seen_chunk_id: str | None = None


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
