"""Idempotent ingestion worker.

Entry point:

    python -m app.workers.ingest

Running ingestion twice on the same RemoteOK data never creates additional job
rows for the same source_url; only scrape_runs, dedup_decisions, last_seen_at,
and updated_at change between runs.
"""

import asyncio
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

import structlog
from pydantic import ValidationError
from sqlalchemy import update

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import dispose_engine, get_sessionmaker
from app.models import ScrapeRun
from app.services.deduplication import upsert_job
from app.services.normalization import clean_text, normalize_record
from app.services.persistence import store_job_skills, upsert_company
from app.services.role_filter import is_software_role
from app.services.skill_extraction import SkillExtractor
from app.services.taxonomy import load_taxonomy, seed_skills
from app.sources.base import SourceError
from app.sources.remoteok import (
    RawRemoteOKJob,
    fetch_raw_records,
    resolve_source_url,
    strip_metadata,
)

log = structlog.get_logger("workers.ingest")

SOURCE = "remoteok"
FAILURE_ERROR_RATIO = 0.50


@dataclass
class Counters:
    records_seen: int = 0
    records_skipped: int = 0
    jobs_inserted: int = 0
    jobs_updated: int = 0
    duplicates_found: int = 0
    error_count: int = 0


async def _start_run() -> uuid.UUID:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        run = ScrapeRun(source=SOURCE, status="running", started_at=datetime.now(UTC))
        session.add(run)
        await session.commit()
        return run.id


async def _finalize_run(
    run_id: uuid.UUID,
    status: str,
    counters: Counters,
    started_monotonic: float,
    error_message: str | None,
) -> int:
    duration_ms = int((time.monotonic() - started_monotonic) * 1000)
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        await session.execute(
            update(ScrapeRun)
            .where(ScrapeRun.id == run_id)
            .values(
                status=status,
                finished_at=datetime.now(UTC),
                duration_ms=duration_ms,
                records_seen=counters.records_seen,
                records_skipped=counters.records_skipped,
                jobs_inserted=counters.jobs_inserted,
                jobs_updated=counters.jobs_updated,
                duplicates_found=counters.duplicates_found,
                error_count=counters.error_count,
                error_message=error_message,
            )
        )
        await session.commit()
    return duration_ms


def _log_summary(status: str, duration_ms: int, counters: Counters) -> None:
    log.info(
        "ingestion_summary",
        source=SOURCE,
        status=status,
        duration_ms=duration_ms,
        **asdict(counters),
    )


async def _process_record(
    record: dict[str, Any],
    extractor: SkillExtractor,
    skill_ids: dict[str, uuid.UUID],
    counters: Counters,
) -> None:
    try:
        raw = RawRemoteOKJob.model_validate(record)
    except ValidationError as exc:
        log.warning("invalid_record", error=str(exc))
        counters.records_skipped += 1
        return

    source_url = resolve_source_url(raw)
    if source_url is None:
        log.warning("missing_stable_source_url", record_id=str(raw.id))
        counters.records_skipped += 1
        return

    title = clean_text(raw.position)
    company_name = clean_text(raw.company)
    if not title or not company_name:
        log.warning("missing_required_fields", source_url=source_url)
        counters.records_skipped += 1
        return

    normalized = normalize_record(raw, source_url, record)
    if not is_software_role(normalized.title, normalized.tags, normalized.description):
        counters.records_skipped += 1
        return

    sessionmaker = get_sessionmaker()
    try:
        async with sessionmaker() as session:
            company_id = await upsert_company(
                session, normalized.company_name, normalized.company_normalized_name
            )
            result = await upsert_job(session, normalized, company_id)
            matches = extractor.extract(normalized.tags, normalized.description)
            await store_job_skills(session, result.canonical_job_id, matches, skill_ids)
            await session.commit()
    except Exception as exc:
        log.warning("record_persist_failed", source_url=source_url, error=str(exc))
        counters.error_count += 1
        return

    if result.action == "inserted_new":
        counters.jobs_inserted += 1
    elif result.action == "updated_existing":
        counters.jobs_updated += 1
    else:
        counters.duplicates_found += 1


async def run_ingestion() -> uuid.UUID:
    """Run one full ingestion cycle. Returns the scrape run id."""
    started_monotonic = time.monotonic()
    run_id = await _start_run()
    counters = Counters()

    try:
        raw_records = await fetch_raw_records()
    except SourceError as exc:
        counters.error_count += 1
        duration_ms = await _finalize_run(run_id, "failed", counters, started_monotonic, str(exc))
        _log_summary("failed", duration_ms, counters)
        raise

    job_records = strip_metadata(raw_records)
    counters.records_seen = len(job_records)

    taxonomy = load_taxonomy()
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        skill_ids = await seed_skills(session, taxonomy)
        await session.commit()
    extractor = SkillExtractor(taxonomy)

    for record in job_records:
        await _process_record(record, extractor, skill_ids, counters)

    persisted = counters.jobs_inserted + counters.jobs_updated + counters.duplicates_found
    attempted = persisted + counters.error_count
    failed = (attempted > 0 and persisted == 0 and counters.error_count > 0) or (
        counters.error_count / max(counters.records_seen, 1) > FAILURE_ERROR_RATIO
    )
    status = "failed" if failed else "success"
    error_message = (
        f"{counters.error_count} record errors out of {counters.records_seen} seen"
        if failed
        else None
    )
    duration_ms = await _finalize_run(run_id, status, counters, started_monotonic, error_message)
    _log_summary(status, duration_ms, counters)
    return run_id


async def _run_and_dispose() -> None:
    try:
        await run_ingestion()
    finally:
        await dispose_engine()


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    asyncio.run(_run_and_dispose())


if __name__ == "__main__":
    main()
