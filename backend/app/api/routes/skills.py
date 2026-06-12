"""GET /top-skills - skill demand counts with trend direction."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.models import Job, JobSkill, Skill
from app.schemas.skills import TopSkillItem, TopSkillsResponse

router = APIRouter()

_ALLOWED_CATEGORIES = {
    "languages",
    "frameworks",
    "cloud",
    "databases",
    "infrastructure",
    "data",
    "ml_adjacent",
}

TREND_THRESHOLD = 0.05


def _trend_direction(current: int, previous: int) -> str:
    if previous == 0:
        return "new" if current > 0 else "stable"
    if current > previous * (1 + TREND_THRESHOLD):
        return "up"
    if current < previous * (1 - TREND_THRESHOLD):
        return "down"
    return "stable"


@router.get("/top-skills", response_model=TopSkillsResponse)
async def top_skills(
    session: AsyncSession = Depends(get_session),
    limit: int = Query(20, ge=1, le=100),
    category: str | None = Query(None),
    days: int = Query(30, ge=1, le=365),
) -> TopSkillsResponse:
    if category is not None and category not in _ALLOWED_CATEGORIES:
        raise HTTPException(status_code=422, detail=f"Invalid category {category!r}")

    now = datetime.now(UTC)
    current_start = now - timedelta(days=days)
    previous_start = current_start - timedelta(days=days)

    event_time = func.coalesce(Job.posted_at, Job.collected_at)
    current_count = func.count(JobSkill.job_id).filter(event_time >= current_start)
    previous_count = func.count(JobSkill.job_id).filter(
        event_time >= previous_start, event_time < current_start
    )

    stmt = (
        select(
            Skill.canonical_name,
            Skill.category,
            current_count.label("current_count"),
            previous_count.label("prev_count"),
        )
        .select_from(JobSkill)
        .join(Skill, Skill.id == JobSkill.skill_id)
        .join(Job, Job.id == JobSkill.job_id)
        .where(Job.is_duplicate.is_(False), event_time >= previous_start)
        .group_by(Skill.id, Skill.canonical_name, Skill.category)
        .having(current_count > 0)
        .order_by(desc("current_count"), Skill.canonical_name)
        .limit(limit)
    )
    if category is not None:
        stmt = stmt.where(Skill.category == category)

    rows = (await session.execute(stmt)).all()

    items = []
    for rank, row in enumerate(rows, start=1):
        current = int(row.current_count)
        previous = int(row.prev_count)
        direction = _trend_direction(current, previous)
        items.append(
            TopSkillItem(
                skill=row.canonical_name,
                category=row.category,
                count=current,
                rank=rank,
                prev_count=None if direction == "new" else previous,
                trend_direction=direction,
            )
        )

    return TopSkillsResponse(items=items, window_days=days, as_of=now)
