from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_achievements_service
from app.db.database import get_db
from app.schemas.engagement import AchievementsResponse
from app.services.achievements_service import AchievementsService

router = APIRouter(prefix="/achievements", tags=["engagement"])


@router.get("", response_model=AchievementsResponse)
def get_achievements(
    db: Session = Depends(get_db),
    service: AchievementsService = Depends(get_achievements_service),
) -> AchievementsResponse:
    return service.get_achievements(db)
