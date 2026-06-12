# Deployment Guide

## 1. PostgreSQL setup

Any PostgreSQL 16 instance works. Two common options:

### Local

```bash
createdb jobmarket
# DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/jobmarket
```

### Neon (hosted)

Create a project at https://neon.tech, then use the connection string with the `asyncpg` driver and SSL:

```text
DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@ep-xxxx.region.aws.neon.tech/dbname?ssl=require
```

Note the scheme must be `postgresql+asyncpg://` (not plain `postgresql://`), and `?ssl=require` enables TLS for asyncpg.

## 2. Required environment variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `DATABASE_URL` | yes (outside tests) | — | PostgreSQL connection string |
| `ENV` | no | `local` | `local`, `test`, or `production` |
| `LOG_LEVEL` | no | `info` | Log verbosity |
| `SCRAPE_TIMEOUT_SECONDS` | no | `30` | RemoteOK request timeout |
| `FRESHNESS_THRESHOLD_HOURS` | no | `25` | Health freshness window |
| `REMOTEOK_USER_AGENT` | no | `job-market-intelligence/1.0` | User-Agent for RemoteOK |
| `TEST_DATABASE_URL` | tests only | — | Test database (ENV=test) |

Never commit `.env`; use `.env.example` as the template.

## 3. Migrations

Run before starting the API or ingestion:

```bash
alembic upgrade head
```

In the Docker image, `alembic upgrade head` runs automatically in the container start command before Uvicorn starts. Migrations never run inside request handlers.

## 4. Backend deployment

### Docker

```bash
cd backend
docker build -t job-market-backend .
docker run -e DATABASE_URL="postgresql+asyncpg://..." -p 8000:8000 job-market-backend
```

The image runs as a non-root user and bakes in no secrets; `DATABASE_URL` is supplied at runtime.

### Bare process

```bash
pip install .
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 5. Scheduled ingestion

The GitHub Actions workflow `.github/workflows/scrape.yml` runs ingestion every 6 hours and on manual dispatch.

Setup:

1. In the GitHub repository, add a secret named `DATABASE_URL` with the production connection string (Settings → Secrets and variables → Actions).
2. The workflow runs `alembic upgrade head` before `python -m app.workers.ingest`, so migrations are always applied first.

Alternatively, run `python -m app.workers.ingest` from any scheduler (cron, systemd timer) with `DATABASE_URL` set.

## 6. Deployment verification

```bash
# 1. Migrations applied cleanly
alembic upgrade head            # exits 0

# 2. Ingestion inserts jobs
python -m app.workers.ingest    # summary log shows jobs_inserted > 0 on first run

# 3. API is healthy and fresh
curl http://localhost:8000/health
# expect: "status": "ok", "freshness_ok": true after a successful ingestion

# 4. Data is served
curl "http://localhost:8000/jobs?limit=5"
curl "http://localhost:8000/top-skills?days=30"
```
