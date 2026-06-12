"""Company upserts and job-skill storage."""

import uuid
from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Company, JobSkill
from app.services.skill_extraction import SkillMatch


async def upsert_company(session: AsyncSession, name: str, normalized_name: str) -> uuid.UUID:
    """Upsert a company by normalized_name; on conflict only the seen/updated
    timestamps change, preserving the originally stored display name."""
    now = datetime.now(UTC)
    stmt = (
        pg_insert(Company)
        .values(
            id=uuid.uuid4(),
            name=name,
            normalized_name=normalized_name,
            first_seen_at=now,
            last_seen_at=now,
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_update(
            index_elements=["normalized_name"],
            set_={"last_seen_at": now, "updated_at": now},
        )
        .returning(Company.id)
    )
    result = await session.execute(stmt)
    return result.scalar_one()


async def store_job_skills(
    session: AsyncSession,
    job_id: uuid.UUID,
    matches: list[SkillMatch],
    skill_ids: dict[str, uuid.UUID],
) -> None:
    """Store skill matches for a job (the canonical job for duplicates).

    On conflict (job_id, skill_id), the row is updated only when the new
    confidence is higher.
    """
    for match in matches:
        skill_id = skill_ids.get(match.canonical_name)
        if skill_id is None:
            continue
        stmt = pg_insert(JobSkill).values(
            job_id=job_id,
            skill_id=skill_id,
            confidence=match.confidence,
            matched_text=match.matched_text,
            match_type=match.match_type,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["job_id", "skill_id"],
            set_={
                "confidence": stmt.excluded.confidence,
                "matched_text": stmt.excluded.matched_text,
                "match_type": stmt.excluded.match_type,
            },
            where=JobSkill.__table__.c.confidence < stmt.excluded.confidence,
        )
        await session.execute(stmt)
