"""Test fixtures.

ENV=test is forced before any app import. Database tests require
TEST_DATABASE_URL (PostgreSQL); they never fall back to DATABASE_URL.
"""

import os

os.environ["ENV"] = "test"

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from alembic import command  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[1]

_TABLES = ["job_skills", "dedup_decisions", "jobs", "scrape_runs", "skills", "companies"]


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        raise RuntimeError(
            "TEST_DATABASE_URL is required for database tests "
            "(PostgreSQL; tests never fall back to DATABASE_URL)."
        )
    return url


@pytest.fixture(scope="session")
def migrated_db(database_url: str) -> str:
    """Run Alembic migrations against the test database once per session."""
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(config, "head")
    return database_url


@pytest_asyncio.fixture
async def db_engine(migrated_db: str):
    """Per-test engine with truncated tables for isolation."""
    engine = create_async_engine(migrated_db, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {', '.join(_TABLES)} CASCADE"))
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    sessionmaker = async_sessionmaker(db_engine, expire_on_commit=False)
    async with sessionmaker() as session:
        yield session


@pytest_asyncio.fixture
async def api_client(db_engine):
    """HTTP client against the app, backed by the migrated test database."""
    from httpx import ASGITransport, AsyncClient

    from app.db.session import dispose_engine
    from app.main import app

    await dispose_engine()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    await dispose_engine()
