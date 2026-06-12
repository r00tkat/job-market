"""GET /health - service, database, and data freshness status."""

import time
from datetime import UTC, datetime, timedelta

import structlog
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text

from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.models import Job, ScrapeRun
from app.schemas.common import to_utc_iso

router = APIRouter()
log = structlog.get_logger("api.health")

DEGRADED_LATENCY_MS = 500


@router.get("/health")
async def health() -> JSONResponse:
    settings = get_settings()
    now = datetime.now(UTC)
    try:
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            start = time.perf_counter()
            await session.execute(text("select 1"))
            db_latency_ms = int(round((time.perf_counter() - start) * 1000))
            jobs_total = (
                await session.execute(select(func.count(Job.id)).where(Job.is_duplicate.is_(False)))
            ).scalar_one()
            last_scrape_at = (
                await session.execute(
                    select(
                        func.max(func.coalesce(ScrapeRun.finished_at, ScrapeRun.started_at))
                    ).where(ScrapeRun.status == "success")
                )
            ).scalar_one_or_none()
    except Exception as exc:
        log.warning("health_db_unreachable", error=str(exc))
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "db_latency_ms": None,
                "last_scrape_at": None,
                "jobs_total": None,
                "freshness_ok": False,
            },
        )

    freshness_window = timedelta(hours=settings.freshness_threshold_hours)
    freshness_ok = last_scrape_at is not None and last_scrape_at >= now - freshness_window
    status = "ok" if db_latency_ms <= DEGRADED_LATENCY_MS else "degraded"
    return JSONResponse(
        status_code=200,
        content={
            "status": status,
            "db_latency_ms": db_latency_ms,
            "last_scrape_at": to_utc_iso(last_scrape_at) if last_scrape_at else None,
            "jobs_total": jobs_total,
            "freshness_ok": freshness_ok,
        },
    )
