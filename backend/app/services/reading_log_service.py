from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.repositories import book_repository, engagement_repository
from app.schemas.engagement import ReadingLogDay, ReadingLogResponse


def today_utc() -> date:
    return datetime.now(timezone.utc).date()


def compute_streaks(activity_dates: set[date]) -> tuple[int, int]:
    """(current_streak, longest_streak) in consecutive calendar days.

    The current streak anchors on today if logged, else yesterday -- so the
    streak isn't shown as broken before the reader has had a chance to read
    today."""
    if not activity_dates:
        return 0, 0

    today = today_utc()
    anchor = today if today in activity_dates else today - timedelta(days=1)
    current = 0
    cursor = anchor
    while cursor in activity_dates:
        current += 1
        cursor -= timedelta(days=1)

    longest = 0
    run = 0
    previous: date | None = None
    for day in sorted(activity_dates):
        run = run + 1 if previous is not None and day == previous + timedelta(days=1) else 1
        longest = max(longest, run)
        previous = day

    return current, longest


class ReadingLogService:
    def log_activity(
        self, db: Session, book_id: str, *, current_page: int | None, current_chapter: int | None
    ) -> None:
        engagement_repository.upsert_reading_log(
            db,
            book_id=book_id,
            activity_date=today_utc(),
            current_page=current_page,
            current_chapter=current_chapter,
        )

    def get_log(self, db: Session, *, limit_days: int = 60) -> ReadingLogResponse:
        entries = engagement_repository.list_reading_log(db, limit_days=limit_days)
        books_by_id = {book.id: book for book in book_repository.list_books(db)}

        days = [
            ReadingLogDay(
                date=entry.activity_date,
                book_id=entry.book_id,
                book_title=books_by_id[entry.book_id].title if entry.book_id in books_by_id else "Unknown book",
                current_page=entry.current_page,
                current_chapter=entry.current_chapter,
            )
            for entry in entries
        ]
        current_streak, longest_streak = compute_streaks(set(engagement_repository.list_all_activity_dates(db)))
        return ReadingLogResponse(days=days, current_streak=current_streak, longest_streak=longest_streak)
