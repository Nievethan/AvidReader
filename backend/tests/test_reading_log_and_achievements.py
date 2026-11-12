from __future__ import annotations

from datetime import timedelta

from app.db import database
from app.models.engagement import ReadingLogEntry
from app.services.reading_log_service import compute_streaks, today_utc
from tests.conftest import make_minimal_pdf_bytes, upload


def test_updating_progress_logs_todays_reading(client):
    book = upload(client, make_minimal_pdf_bytes())
    res = client.put(f"/api/v1/books/{book['id']}/progress", json={"current_page": 5})
    assert res.status_code == 200

    log = client.get("/api/v1/reading-log").json()
    assert log["current_streak"] == 1
    assert log["longest_streak"] == 1
    assert len(log["days"]) == 1
    assert log["days"][0]["book_id"] == book["id"]
    assert log["days"][0]["current_page"] == 5


def test_same_day_progress_updates_do_not_duplicate_the_log(client):
    book = upload(client, make_minimal_pdf_bytes())
    client.put(f"/api/v1/books/{book['id']}/progress", json={"current_page": 1})
    client.put(f"/api/v1/books/{book['id']}/progress", json={"current_page": 2})

    log = client.get("/api/v1/reading-log").json()
    assert len(log["days"]) == 1
    assert log["days"][0]["current_page"] == 2


def test_streak_spans_consecutive_days(client):
    book = upload(client, make_minimal_pdf_bytes())
    client.put(f"/api/v1/books/{book['id']}/progress", json={"current_page": 1})

    # Backfill two earlier consecutive days directly, as if the reader had
    # been active on them too.
    with database.SessionLocal() as db:
        today = today_utc()
        db.add(ReadingLogEntry(book_id=book["id"], activity_date=today - timedelta(days=1), current_page=1))
        db.add(ReadingLogEntry(book_id=book["id"], activity_date=today - timedelta(days=2), current_page=1))
        db.commit()

    log = client.get("/api/v1/reading-log").json()
    assert log["current_streak"] == 3
    assert log["longest_streak"] == 3


def test_compute_streaks_anchors_on_yesterday_if_not_read_today():
    today = today_utc()
    dates = {today - timedelta(days=1), today - timedelta(days=2)}
    current, longest = compute_streaks(dates)
    assert current == 2
    assert longest == 2


def test_compute_streaks_empty():
    assert compute_streaks(set()) == (0, 0)


def test_achievements_unlock_progressively(client):
    res = client.get("/api/v1/achievements").json()
    by_id = {a["id"]: a["unlocked"] for a in res["achievements"]}
    assert by_id["first_upload"] is False
    assert by_id["finished_a_book"] is False
    assert by_id["first_question"] is False

    book = upload(client, make_minimal_pdf_bytes())
    res = client.get("/api/v1/achievements").json()
    by_id = {a["id"]: a["unlocked"] for a in res["achievements"]}
    assert by_id["first_upload"] is True
    assert by_id["finished_a_book"] is False

    client.put(f"/api/v1/books/{book['id']}/progress", json={"percent_complete": 100})
    res = client.get("/api/v1/achievements").json()
    by_id = {a["id"]: a["unlocked"] for a in res["achievements"]}
    assert by_id["finished_a_book"] is True


def test_first_question_achievement_unlocks_after_a_chat_message(client):
    book = upload(client, make_minimal_pdf_bytes())
    client.post(
        "/api/v1/ai/chat",
        json={"book_id": book["id"], "question": "Who is the narrator?"},
    )
    res = client.get("/api/v1/achievements").json()
    by_id = {a["id"]: a["unlocked"] for a in res["achievements"]}
    assert by_id["first_question"] is True
