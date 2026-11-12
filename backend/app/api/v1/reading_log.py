from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_reading_log_service
from app.db.database import get_db
from app.schemas.engagement import ReadingLogResponse
from app.services.reading_log_service import ReadingLogService

router = APIRouter(prefix="/reading-log", tags=["engagement"])


@router.get("", response_model=ReadingLogResponse)
def get_reading_log(
    db: Session = Depends(get_db),
    service: ReadingLogService = Depends(get_reading_log_service),
) -> ReadingLogResponse:
    """Across all books -- not scoped to one, matching the dashboard-level
    reading log in the original design (not a per-book feature)."""
    return service.get_log(db)
