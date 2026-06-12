"""Deduplication: exact source-URL pass, then content-hash pass.

Fuzzy candidate logging (Pass 3) is intentionally omitted in Phase 1; the spec
allows omitting it entirely, and fuzzy matches must never be auto-deduplicated.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DedupDecision, Job
from app.services.normalization import NormalizedJob

CONTENT_HASH_WINDOW_DAYS = 30

DedupAction = Literal["inserted_new", "updated_existing", "marked_duplicate"]


@dataclass(frozen=True)
class DedupResult:
    action: DedupAction
    job_id: uuid.UUID
    # The job that skills should be stored against (the canonical job when the
    # incoming record is a duplicate).
    canonical_job_id: uuid.UUID


async def upsert_job(
    session: AsyncSession, normalized: NormalizedJob, company_id: uuid.UUID
) -> DedupResult:
    """Insert or update a job using the deduplication passes, in order."""
    now = datetime.now(UTC)

    # Pass 1 - exact source URL.
    result = await session.execute(
        select(Job).where(Job.source_url == normalized.source_url).limit(1)
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        existing.title = normalized.title
        existing.location = normalized.location
        existing.employment_type = normalized.employment_type
        existing.salary_min = normalized.salary_min
        existing.salary_max = normalized.salary_max
        existing.salary_currency = normalized.salary_currency
        existing.remote_type = normalized.remote_type
        existing.description = normalized.description
        existing.description_html = normalized.description_html
        existing.content_hash = normalized.content_hash
        existing.raw_payload = normalized.raw_payload
        existing.last_seen_at = now
        existing.updated_at = now
        # id, source_url, source, source_id, posted_at, is_duplicate,
        # canonical_id, and created_at are never updated here.
        session.add(
            DedupDecision(
                incoming_source=normalized.source,
                incoming_source_url=normalized.source_url,
                matched_job_id=existing.id,
                pass_name="url_match",
                match_signal=normalized.source_url,
                action="updated_existing",
            )
        )
        canonical_id = (
            existing.canonical_id
            if existing.is_duplicate and existing.canonical_id is not None
            else existing.id
        )
        return DedupResult("updated_existing", existing.id, canonical_id)

    # Pass 2 - content hash against recent canonical jobs.
    window_start = now - timedelta(days=CONTENT_HASH_WINDOW_DAYS)
    hash_result = await session.execute(
        select(Job.id)
        .where(
            Job.content_hash == normalized.content_hash,
            Job.is_duplicate.is_(False),
            func.coalesce(Job.posted_at, Job.collected_at) >= window_start,
        )
        .limit(1)
    )
    canonical_match = hash_result.scalar_one_or_none()

    job = Job(
        id=uuid.uuid4(),
        company_id=company_id,
        title=normalized.title,
        location=normalized.location,
        employment_type=normalized.employment_type,
        salary_min=normalized.salary_min,
        salary_max=normalized.salary_max,
        salary_currency=normalized.salary_currency,
        remote_type=normalized.remote_type,
        description=normalized.description,
        description_html=normalized.description_html,
        source=normalized.source,
        source_id=normalized.source_id,
        source_url=normalized.source_url,
        posted_at=normalized.posted_at,
        collected_at=now,
        last_seen_at=now,
        content_hash=normalized.content_hash,
        raw_payload=normalized.raw_payload,
        is_duplicate=canonical_match is not None,
        canonical_id=canonical_match,
        created_at=now,
        updated_at=now,
    )
    session.add(job)
    await session.flush()

    if canonical_match is not None:
        session.add(
            DedupDecision(
                incoming_source=normalized.source,
                incoming_source_url=normalized.source_url,
                matched_job_id=canonical_match,
                pass_name="content_hash",
                match_signal=normalized.content_hash,
                action="marked_duplicate",
            )
        )
        return DedupResult("marked_duplicate", job.id, canonical_match)

    return DedupResult("inserted_new", job.id, job.id)
