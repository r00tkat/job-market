"""Response schemas for GET /top-skills."""

from pydantic import BaseModel

from app.schemas.common import UtcDatetime


class TopSkillItem(BaseModel):
    skill: str
    category: str
    count: int
    rank: int
    prev_count: int | None
    trend_direction: str


class TopSkillsResponse(BaseModel):
    items: list[TopSkillItem]
    window_days: int
    as_of: UtcDatetime
