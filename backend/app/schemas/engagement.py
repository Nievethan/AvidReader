from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class ReadingLogDay(BaseModel):
    date: date
    book_id: str
    book_title: str
    current_page: int | None = None
    current_chapter: int | None = None


class ReadingLogResponse(BaseModel):
    days: list[ReadingLogDay]
    current_streak: int
    longest_streak: int


class Achievement(BaseModel):
    id: str
    label: str
    description: str
    unlocked: bool


class AchievementsResponse(BaseModel):
    achievements: list[Achievement]
    current_streak: int
    longest_streak: int
