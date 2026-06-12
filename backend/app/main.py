"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI
from fastapi.responses import FileResponse

from app.api.errors import register_exception_handlers
from app.api.middleware import RequestContextMiddleware
from app.api.routes import health, jobs, skills
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import dispose_engine, get_sessionmaker
from app.services.taxonomy import load_taxonomy, seed_skills

log = structlog.get_logger("api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    # Load the taxonomy and seed the skills table at startup. A DB outage here
    # must not prevent the app from starting: /health reports DB status.
    try:
        taxonomy = load_taxonomy()
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            await seed_skills(session, taxonomy)
            await session.commit()
        log.info("skills_seeded", count=len(taxonomy))
    except Exception as exc:
        log.warning("skill_seed_failed", error=str(exc))
    yield
    await dispose_engine()


app = FastAPI(title="Job Market Intelligence API", version="0.1.0", lifespan=lifespan)
app.add_middleware(RequestContextMiddleware)
register_exception_handlers(app)
app.include_router(health.router)
app.include_router(jobs.router)
app.include_router(skills.router)

_STATIC_DIR = Path(__file__).resolve().parent / "static"


@app.get("/", include_in_schema=False)
async def dashboard() -> FileResponse:
    """Serve the Phase 2 dashboard."""
    return FileResponse(_STATIC_DIR / "index.html")
