"""Integration tests for the REST API (PostgreSQL required)."""

import uuid
from datetime import UTC, datetime, timedelta

from app.models import Company, JobSkill, ScrapeRun, Skill
from tests.helpers import make_job


async def _seed_company(db_session, name="Acme") -> uuid.UUID:
    company = Company(id=uuid.uuid4(), name=name, normalized_name=name.lower())
    db_session.add(company)
    await db_session.flush()
    return company.id


async def _seed_skill(db_session, canonical_name, category, aliases) -> uuid.UUID:
    skill = Skill(
        id=uuid.uuid4(), canonical_name=canonical_name, category=category, aliases=aliases
    )
    db_session.add(skill)
    await db_session.flush()
    return skill.id


# ---------------------------------------------------------------- /health


async def test_health_returns_expected_fields(api_client, db_session):
    response = await api_client.get("/health")
    assert response.status_code == 200
    body = response.json()
    # "ok" on a local/fast DB; "degraded" is correct when DB latency > 500ms
    # (e.g. a remote cloud database). Both are healthy HTTP 200 states.
    assert body["status"] in ("ok", "degraded")
    assert isinstance(body["db_latency_ms"], int)
    assert body["jobs_total"] == 0
    assert body["last_scrape_at"] is None
    assert body["freshness_ok"] is False
    assert "X-Request-ID" in response.headers


async def test_health_freshness_with_recent_successful_run(api_client, db_session):
    db_session.add(
        ScrapeRun(
            id=uuid.uuid4(),
            source="remoteok",
            status="success",
            started_at=datetime.now(UTC) - timedelta(hours=1),
            finished_at=datetime.now(UTC) - timedelta(hours=1),
        )
    )
    await db_session.commit()
    response = await api_client.get("/health")
    body = response.json()
    assert body["freshness_ok"] is True
    assert body["last_scrape_at"] is not None


async def test_health_returns_503_when_db_unreachable(api_client, monkeypatch):
    import app.api.routes.health as health_module

    def boom():
        raise RuntimeError("database unreachable")

    monkeypatch.setattr(health_module, "get_sessionmaker", boom)
    response = await api_client.get("/health")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "error"
    assert body["freshness_ok"] is False


# ---------------------------------------------------------------- /jobs


async def test_jobs_returns_real_database_records(api_client, db_session):
    company_id = await _seed_company(db_session)
    db_session.add(make_job(company_id, title="Backend Engineer"))
    await db_session.commit()

    response = await api_client.get("/jobs")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Backend Engineer"
    assert body["items"][0]["company"]["name"] == "Acme"
    assert body["items"][0]["source"] == "remoteok"


async def test_jobs_excludes_duplicates(api_client, db_session):
    company_id = await _seed_company(db_session)
    canonical = make_job(company_id, title="Canonical Job")
    db_session.add(canonical)
    await db_session.flush()
    db_session.add(
        make_job(company_id, title="Duplicate Job", is_duplicate=True, canonical_id=canonical.id)
    )
    await db_session.commit()

    response = await api_client.get("/jobs")
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Canonical Job"


async def test_jobs_pagination_and_total(api_client, db_session):
    company_id = await _seed_company(db_session)
    for index in range(5):
        db_session.add(make_job(company_id, title=f"Job {index}"))
    await db_session.commit()

    response = await api_client.get("/jobs", params={"limit": 2, "offset": 0})
    body = response.json()
    assert body["total"] == 5  # full filtered count, not page size
    assert len(body["items"]) == 2
    assert body["limit"] == 2

    response_2 = await api_client.get("/jobs", params={"limit": 2, "offset": 4})
    assert len(response_2.json()["items"]) == 1


async def test_jobs_sorting_by_title(api_client, db_session):
    company_id = await _seed_company(db_session)
    for title in ["Charlie", "Alpha", "Bravo"]:
        db_session.add(make_job(company_id, title=title))
    await db_session.commit()

    response = await api_client.get("/jobs", params={"sort": "title"})
    titles = [item["title"] for item in response.json()["items"]]
    assert titles == ["Alpha", "Bravo", "Charlie"]

    response_desc = await api_client.get("/jobs", params={"sort": "-title"})
    titles_desc = [item["title"] for item in response_desc.json()["items"]]
    assert titles_desc == ["Charlie", "Bravo", "Alpha"]


async def test_jobs_filters(api_client, db_session):
    company_id = await _seed_company(db_session)
    db_session.add(make_job(company_id, title="Remote FT", remote_type="remote"))
    db_session.add(
        make_job(company_id, title="Hybrid CT", remote_type="hybrid", employment_type="contract")
    )
    await db_session.commit()

    response = await api_client.get("/jobs", params={"remote_type": "hybrid"})
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Hybrid CT"

    response = await api_client.get("/jobs", params={"employment_type": "contract"})
    assert response.json()["total"] == 1

    response = await api_client.get("/jobs", params={"source": "remoteok"})
    assert response.json()["total"] == 2


async def test_jobs_skill_filter_resolves_aliases(api_client, db_session):
    company_id = await _seed_company(db_session)
    skill_id = await _seed_skill(db_session, "PostgreSQL", "databases", ["postgres", "pg"])
    job_with = make_job(company_id, title="With Skill")
    job_without = make_job(company_id, title="Without Skill")
    db_session.add_all([job_with, job_without])
    await db_session.flush()
    db_session.add(
        JobSkill(
            job_id=job_with.id,
            skill_id=skill_id,
            confidence=1.0,
            matched_text="postgres",
            match_type="tag",
        )
    )
    await db_session.commit()

    # Canonical name, case-insensitive.
    response = await api_client.get("/jobs", params={"skill": "postgresql"})
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "With Skill"
    assert body["items"][0]["skills"][0]["canonical_name"] == "PostgreSQL"

    # Alias.
    response = await api_client.get("/jobs", params={"skill": "pg"})
    assert response.json()["total"] == 1

    # Unknown skill -> empty result set.
    response = await api_client.get("/jobs", params={"skill": "cobol"})
    body = response.json()
    assert body["total"] == 0
    assert body["items"] == []


async def test_jobs_unknown_sort_returns_422_standard_shape(api_client, db_session):
    response = await api_client.get("/jobs", params={"sort": "salary"})
    assert response.status_code == 422
    body = response.json()
    assert set(body.keys()) == {"error", "code", "request_id"}
    assert body["code"] == "VALIDATION_ERROR"


async def test_jobs_invalid_limit_returns_standard_error_shape(api_client, db_session):
    response = await api_client.get("/jobs", params={"limit": 0})
    assert response.status_code == 422
    body = response.json()
    assert set(body.keys()) == {"error", "code", "request_id"}
    assert body["code"] == "VALIDATION_ERROR"
    assert response.headers["X-Request-ID"] == body["request_id"]


# ---------------------------------------------------------------- /top-skills


async def _seed_top_skills_data(db_session):
    """new: current 2 / prev 0; up: 3/1; down: 1/3; stable: 2/2."""
    company_id = await _seed_company(db_session)
    now = datetime.now(UTC)
    current = now - timedelta(days=5)
    previous = now - timedelta(days=35)

    counts = {
        "Python": (3, 1),  # up
        "React": (1, 3),  # down
        "Rust": (2, 2),  # stable
        "Kotlin": (2, 0),  # new
    }
    for name, (current_n, previous_n) in counts.items():
        skill_id = await _seed_skill(db_session, name, "languages", [])
        for _ in range(current_n):
            job = make_job(company_id, title=f"{name} Engineer", posted_at=current)
            db_session.add(job)
            await db_session.flush()
            db_session.add(
                JobSkill(
                    job_id=job.id,
                    skill_id=skill_id,
                    confidence=1.0,
                    matched_text=name,
                    match_type="tag",
                )
            )
        for _ in range(previous_n):
            job = make_job(company_id, title=f"{name} Engineer Old", posted_at=previous)
            db_session.add(job)
            await db_session.flush()
            db_session.add(
                JobSkill(
                    job_id=job.id,
                    skill_id=skill_id,
                    confidence=1.0,
                    matched_text=name,
                    match_type="tag",
                )
            )
    await db_session.commit()


async def test_top_skills_counts_and_trends(api_client, db_session):
    await _seed_top_skills_data(db_session)
    response = await api_client.get("/top-skills", params={"days": 30})
    assert response.status_code == 200
    body = response.json()
    assert body["window_days"] == 30
    assert body["as_of"]

    by_skill = {item["skill"]: item for item in body["items"]}
    assert by_skill["Python"]["count"] == 3
    assert by_skill["Python"]["trend_direction"] == "up"
    assert by_skill["Python"]["prev_count"] == 1
    assert by_skill["Python"]["rank"] == 1  # highest current count

    assert by_skill["React"]["trend_direction"] == "down"
    assert by_skill["Rust"]["trend_direction"] == "stable"
    assert by_skill["Kotlin"]["trend_direction"] == "new"
    assert by_skill["Kotlin"]["prev_count"] is None


async def test_top_skills_excludes_duplicate_jobs(api_client, db_session):
    company_id = await _seed_company(db_session)
    skill_id = await _seed_skill(db_session, "Python", "languages", [])
    canonical = make_job(company_id, posted_at=datetime.now(UTC) - timedelta(days=1))
    db_session.add(canonical)
    await db_session.flush()
    duplicate = make_job(
        company_id,
        posted_at=datetime.now(UTC) - timedelta(days=1),
        is_duplicate=True,
        canonical_id=canonical.id,
    )
    db_session.add(duplicate)
    await db_session.flush()
    for job_id in (canonical.id, duplicate.id):
        db_session.add(
            JobSkill(
                job_id=job_id,
                skill_id=skill_id,
                confidence=1.0,
                matched_text="python",
                match_type="tag",
            )
        )
    await db_session.commit()

    response = await api_client.get("/top-skills")
    body = response.json()
    assert body["items"][0]["count"] == 1  # duplicate job not counted


async def test_top_skills_category_filter_and_validation(api_client, db_session):
    await _seed_top_skills_data(db_session)
    response = await api_client.get("/top-skills", params={"category": "languages"})
    assert response.status_code == 200
    assert len(response.json()["items"]) == 4

    response = await api_client.get("/top-skills", params={"category": "bogus"})
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"

    response = await api_client.get("/top-skills", params={"days": 0})
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
