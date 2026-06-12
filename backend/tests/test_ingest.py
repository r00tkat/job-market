"""Integration tests for the ingestion worker (PostgreSQL + mocked RemoteOK)."""

import pytest
from sqlalchemy import func, select

from app.models import Job, JobSkill, ScrapeRun
from app.sources.base import RateLimitError
from app.sources.remoteok import REMOTEOK_API_URL
from app.workers.ingest import run_ingestion

METADATA = {"legal": "RemoteOK legal notice"}

SOFTWARE_JOB = {
    "id": 1,
    "slug": "backend-engineer-acme-1",
    "company": "Acme",
    "position": "Backend Engineer",
    "description": "<p>We want experience with Python and PostgreSQL 16.</p>",
    "tags": ["python", "postgres"],
    "location": "Worldwide",
    "salary_min": 100000,
    "salary_max": 140000,
    "epoch": 1781172000,
    "url": "https://remoteok.com/remote-jobs/backend-engineer-acme-1",
}

NON_SOFTWARE_JOB = {
    "id": 2,
    "slug": "marketing-manager-globex-2",
    "company": "Globex",
    "position": "Marketing Manager",
    "description": "<p>Run our ad campaigns.</p>",
    "tags": ["marketing"],
    "url": "https://remoteok.com/remote-jobs/marketing-manager-globex-2",
}

INVALID_JOB = {
    "id": 3,
    "company": "Initech",
    "position": 12345,  # wrong type: fails raw validation
    "slug": "broken-3",
}

PAYLOAD = [METADATA, SOFTWARE_JOB, NON_SOFTWARE_JOB, INVALID_JOB]


@pytest.fixture(autouse=True)
async def _fresh_app_engine(db_engine):
    """Ensure the worker builds its engine against the truncated test DB."""
    from app.db.session import dispose_engine

    await dispose_engine()
    yield
    await dispose_engine()


async def test_ingestion_inserts_software_jobs_and_skips_others(db_session, httpx_mock):
    httpx_mock.add_response(url=REMOTEOK_API_URL, json=PAYLOAD)
    await run_ingestion()

    jobs = (await db_session.execute(select(Job))).scalars().all()
    assert len(jobs) == 1
    assert jobs[0].title == "Backend Engineer"
    assert jobs[0].is_duplicate is False

    run = (await db_session.execute(select(ScrapeRun))).scalar_one()
    assert run.status == "success"
    assert run.records_seen == 3  # metadata excluded
    assert run.records_skipped == 2  # non-software + invalid
    assert run.jobs_inserted == 1
    assert run.error_count == 0
    assert run.finished_at is not None
    assert run.duration_ms is not None

    # Skills were extracted and stored.
    skill_count = (
        await db_session.execute(select(func.count()).select_from(JobSkill))
    ).scalar_one()
    assert skill_count > 0


async def test_ingestion_is_idempotent(db_session, httpx_mock):
    httpx_mock.add_response(url=REMOTEOK_API_URL, json=PAYLOAD)
    httpx_mock.add_response(url=REMOTEOK_API_URL, json=PAYLOAD)
    await run_ingestion()
    await run_ingestion()

    # Second run did not create additional rows for the same source_url.
    total = (await db_session.execute(select(func.count(Job.id)))).scalar_one()
    assert total == 1

    runs = (await db_session.execute(select(ScrapeRun))).scalars().all()
    assert len(runs) == 2
    assert all(run.status == "success" for run in runs)
    second_run = max(runs, key=lambda r: r.started_at)
    assert second_run.jobs_updated == 1
    assert second_run.jobs_inserted == 0


async def test_fetch_failure_marks_run_failed_and_reraises(db_session, httpx_mock):
    httpx_mock.add_response(url=REMOTEOK_API_URL, status_code=429)
    with pytest.raises(RateLimitError):
        await run_ingestion()

    run = (await db_session.execute(select(ScrapeRun))).scalar_one()
    assert run.status == "failed"
    assert run.error_message is not None
