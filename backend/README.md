# Job Market Intelligence Platform — Backend (Phase 1)

A backend that ingests live software-engineering job postings from the RemoteOK public API, normalizes and deduplicates them in PostgreSQL, extracts structured skill signals, and serves job and skill intelligence over a REST API.

## Problem solved

Job-market data for software engineering roles is scattered, noisy, and full of duplicates. This service turns a live job board feed into a clean, deduplicated, queryable dataset with per-skill demand counts and trends, suitable for analytics and dashboards.

## Prerequisites

- Python 3.12
- PostgreSQL 16 (any reachable instance; local or hosted such as Neon)

## Local setup

From the `backend/` directory (5 commands):

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # then set DATABASE_URL to your PostgreSQL instance
alembic upgrade head
python -m app.workers.ingest
```

On Windows, activate with `.venv\Scripts\activate` instead.

## Commands

| Action | Command |
|---|---|
| Run migrations | `alembic upgrade head` |
| Run ingestion | `python -m app.workers.ingest` |
| Start the API | `uvicorn app.main:app --reload` |
| Run tests | `ENV=test TEST_DATABASE_URL=postgresql+asyncpg://test:test@localhost:5432/jobmarket_test pytest` |

## Dashboard

With the API running, open http://localhost:8000 in a browser for the built-in dashboard: live health stats, top-skill demand charts with trends, and a filterable job board. Every listing credits and links back to the original RemoteOK posting.

## Example API calls

```bash
curl http://localhost:8000/health
curl "http://localhost:8000/jobs?limit=5"
curl "http://localhost:8000/jobs?skill=python&remote_type=remote"
curl "http://localhost:8000/top-skills?days=30"
```

## Documentation

- [API.md](API.md) — endpoint reference
- [DEPLOYMENT.md](DEPLOYMENT.md) — deployment guide
- [SOURCE_COMPLIANCE.md](SOURCE_COMPLIANCE.md) — data source usage and attribution
