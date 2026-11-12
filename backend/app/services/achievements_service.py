from __future__ import annotations

from sqlalchemy.orm import Session

from app.repositories import ai_repository, book_repository, engagement_repository
from app.schemas.engagement import Achievement, AchievementsResponse
from app.services.reading_log_service import compute_streaks


def _book_finished(book, progress) -> bool:
    if progress is None:
        return False
    if progress.percent_complete is not None:
        return progress.percent_complete >= 100
    if book.total_pages and progress.current_page is not None:
        return progress.current_page >= book.total_pages
    return False


class AchievementsService:
    """Every achievement is computed live from existing data (books,
    progress, reading log, messages) -- no separate "unlocked" table, so
    there's nothing to get out of sync."""

    def get_achievements(self, db: Session) -> AchievementsResponse:
        books = book_repository.list_books(db)
        current_streak, longest_streak = compute_streaks(set(engagement_repository.list_all_activity_dates(db)))
        any_finished = any(_book_finished(book, book_repository.get_progress(db, book.id)) for book in books)
        asked_question = ai_repository.count_user_messages(db) > 0

        achievements = [
            Achievement(
                id="first_upload",
                label="Shelved your first book",
                description="Upload a book to your library.",
                unlocked=len(books) > 0,
            ),
            Achievement(
                id="first_question",
                label="Curious mind",
                description="Ask the AI your first question about a book.",
                unlocked=asked_question,
            ),
            Achievement(
                id="finished_a_book",
                label="The End",
                description="Finish reading a book.",
                unlocked=any_finished,
            ),
            Achievement(
                id="three_day_streak",
                label="Building a habit",
                description="Read on 3 days in a row.",
                unlocked=current_streak >= 3 or longest_streak >= 3,
            ),
            Achievement(
                id="seven_day_streak",
                label="A week of reading",
                description="Read on 7 days in a row.",
                unlocked=current_streak >= 7 or longest_streak >= 7,
            ),
            Achievement(
                id="library_of_five",
                label="Growing library",
                description="Upload 5 books.",
                unlocked=len(books) >= 5,
            ),
        ]
        return AchievementsResponse(
            achievements=achievements, current_streak=current_streak, longest_streak=longest_streak
        )
