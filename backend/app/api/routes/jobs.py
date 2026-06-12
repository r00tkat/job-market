"""GET /jobs - paginated, filterable job listings (duplicates excluded)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_session
from app.models import Job, JobSkill, Skill
from app.schemas.jobs import CompanyOut, JobOut, JobSkillOut, JobsResponse

router = APIRouter()

_SORTABLE_FIELDS = {"posted_at", "collected_at", "title"}
_ALLOWED_REMOTE_TYPES = {"remote", "hybrid", "onsite", "unknown"}
_ALLOWED_EMPLOYMENT_TYPES = {"full_time", "part_time", "contract", "internship", "unknown"}


async def _resolve_skill_id(session: AsyncSession, name: str) -> uuid.UUID | None:
    """Match canonical_name case-insensitively, then aliases (stored lowercase)."""
    lowered = name.strip().lower()
    result = await session.execute(
        select(Skill.id).where(func.lower(Skill.canonical_name) == lowered).limit(1)
    )
    skill_id = result.scalar_one_or_none()
    if skill_id is not None:
        return skill_id
    result = await session.execute(select(Skill.id).where(Skill.aliases.any(lowered)).limit(1))
    return result.scalar_one_or_none()


def _serialize_job(job: Job) -> JobOut:
    skills = sorted(job.job_skills, key=lambda js: (-float(js.confidence), js.skill.canonical_name))
    return JobOut(
        id=job.id,
        title=job.title,
        company=CompanyOut(id=job.company.id, name=job.company.name, website=job.company.website),
        location=job.location,
        remote_type=job.remote_type,
        employment_type=job.employment_type,
        salary_min=job.salary_min,
        salary_max=job.salary_max,
        salary_currency=job.salary_currency,
        source=job.source,
        source_url=job.source_url,
        posted_at=job.posted_at,
        collected_at=job.collected_at,
        skills=[
            JobSkillOut(
                canonical_name=js.skill.canonical_name,
                category=js.skill.category,
                confidence=float(js.confidence),
            )
            for js in skills
        ],
    )


@router.get("/jobs", response_model=JobsResponse)
async def list_jobs(
    session: AsyncSession = Depends(get_session),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    sort: str = Query("-posted_at"),
    source: str | None = Query(None),
    remote_type: str | None = Query(None),
    employment_type: str | None = Query(None),
    skill: str | None = Query(None),
) -> JobsResponse:
    descending = sort.startswith("-")
    sort_field = sort[1:] if descending else sort
    if sort_field not in _SORTABLE_FIELDS:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown sort field {sort_field!r}; allowed: posted_at, collected_at, title",
        )
    if remote_type is not None and remote_type not in _ALLOWED_REMOTE_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid remote_type {remote_type!r}",
        )
    if employment_type is not None and employment_type not in _ALLOWED_EMPLOYMENT_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid employment_type {employment_type!r}",
        )

    filters = [Job.is_duplicate.is_(False)]
    if source is not None:
        filters.append(Job.source == source)
    if remote_type is not None:
        filters.append(Job.remote_type == remote_type)
    if employment_type is not None:
        filters.append(Job.employment_type == employment_type)

    skill_id: uuid.UUID | None = None
    if skill is not None:
        skill_id = await _resolve_skill_id(session, skill)
        if skill_id is None:
            return JobsResponse(items=[], total=0, limit=limit, offset=offset)

    def apply_filters(stmt: Select) -> Select:
        stmt = stmt.where(*filters)
        if skill_id is not None:
            stmt = stmt.join(JobSkill, JobSkill.job_id == Job.id).where(
                JobSkill.skill_id == skill_id
            )
        return stmt

    total = (await session.execute(apply_filters(select(func.count(Job.id))))).scalar_one()

    sort_columns = {
        "posted_at": Job.posted_at,
        "collected_at": Job.collected_at,
        "title": Job.title,
    }
    column = sort_columns[sort_field]
    primary = column.desc().nulls_last() if descending else column.asc().nulls_last()
    stmt = (
        apply_filters(select(Job))
        .options(
            selectinload(Job.company),
            selectinload(Job.job_skills).selectinload(JobSkill.skill),
        )
        .order_by(primary, Job.collected_at.desc(), Job.id)
        .limit(limit)
        .offset(offset)
    )
    jobs = (await session.execute(stmt)).scalars().all()

    return JobsResponse(
        items=[_serialize_job(job) for job in jobs],
        total=total,
        limit=limit,
        offset=offset,
    )
