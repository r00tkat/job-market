"""Integration tests for deduplication (PostgreSQL required)."""

from sqlalchemy import func, select

from app.models import DedupDecision, Job, JobSkill
from app.services.deduplication import upsert_job
from app.services.persistence import store_job_skills, upsert_company
from app.services.skill_extraction import SkillMatch
from app.services.taxonomy import SkillDefinition, seed_skills
from tests.helpers import make_normalized

URL_A = "https://remoteok.com/remote-jobs/backend-1"
URL_B = "https://remoteok.com/remote-jobs/backend-2"


async def test_same_source_url_updates_existing_row(db_session):
    company_id = await upsert_company(db_session, "Acme", "acme")
    first = make_normalized(source_url=URL_A, description="Original description")
    result_1 = await upsert_job(db_session, first, company_id)
    await db_session.commit()
    assert result_1.action == "inserted_new"

    second = make_normalized(source_url=URL_A, description="Updated description")
    result_2 = await upsert_job(db_session, second, company_id)
    await db_session.commit()

    assert result_2.action == "updated_existing"
    assert result_2.job_id == result_1.job_id

    # No second job row was inserted.
    total = (await db_session.execute(select(func.count(Job.id)))).scalar_one()
    assert total == 1

    # content_hash was updated because the description changed.
    job = (await db_session.execute(select(Job))).scalar_one()
    assert job.description == "Updated description"
    assert job.content_hash == second.content_hash
    assert job.content_hash != first.content_hash


async def test_url_match_creates_dedup_decision(db_session):
    company_id = await upsert_company(db_session, "Acme", "acme")
    await upsert_job(db_session, make_normalized(source_url=URL_A), company_id)
    await upsert_job(db_session, make_normalized(source_url=URL_A), company_id)
    await db_session.commit()

    decisions = (await db_session.execute(select(DedupDecision))).scalars().all()
    url_matches = [d for d in decisions if d.pass_name == "url_match"]
    assert len(url_matches) == 1
    assert url_matches[0].action == "updated_existing"
    assert url_matches[0].incoming_source_url == URL_A


async def test_same_content_hash_different_url_marks_duplicate(db_session):
    company_id = await upsert_company(db_session, "Acme", "acme")
    original = make_normalized(source_url=URL_A)
    result_1 = await upsert_job(db_session, original, company_id)
    await db_session.commit()

    copy = make_normalized(source_url=URL_B)  # same title/company/description
    result_2 = await upsert_job(db_session, copy, company_id)
    await db_session.commit()

    assert result_2.action == "marked_duplicate"
    assert result_2.canonical_job_id == result_1.job_id

    duplicate = (await db_session.execute(select(Job).where(Job.source_url == URL_B))).scalar_one()
    assert duplicate.is_duplicate is True
    assert duplicate.canonical_id == result_1.job_id

    decisions = (
        (
            await db_session.execute(
                select(DedupDecision).where(DedupDecision.pass_name == "content_hash")
            )
        )
        .scalars()
        .all()
    )
    assert len(decisions) == 1
    assert decisions[0].action == "marked_duplicate"


async def test_duplicate_job_skills_stored_against_canonical(db_session):
    skill_ids = await seed_skills(
        db_session,
        [SkillDefinition(canonical_name="Python", category="languages", aliases=["python3"])],
    )
    company_id = await upsert_company(db_session, "Acme", "acme")
    result_1 = await upsert_job(db_session, make_normalized(source_url=URL_A), company_id)
    result_2 = await upsert_job(db_session, make_normalized(source_url=URL_B), company_id)
    assert result_2.action == "marked_duplicate"

    matches = [SkillMatch("Python", 1.0, "python", "tag")]
    await store_job_skills(db_session, result_2.canonical_job_id, matches, skill_ids)
    await db_session.commit()

    rows = (await db_session.execute(select(JobSkill))).scalars().all()
    assert len(rows) == 1
    assert rows[0].job_id == result_1.job_id  # stored against the canonical job


async def test_job_skill_updated_only_with_higher_confidence(db_session):
    skill_ids = await seed_skills(
        db_session,
        [SkillDefinition(canonical_name="Python", category="languages", aliases=[])],
    )
    company_id = await upsert_company(db_session, "Acme", "acme")
    result = await upsert_job(db_session, make_normalized(source_url=URL_A), company_id)

    await store_job_skills(
        db_session, result.job_id, [SkillMatch("Python", 0.9, "ctx", "contextual")], skill_ids
    )
    # Lower confidence must not overwrite.
    await store_job_skills(
        db_session, result.job_id, [SkillMatch("Python", 0.8, "exact", "exact")], skill_ids
    )
    await db_session.commit()
    row = (await db_session.execute(select(JobSkill))).scalar_one()
    assert float(row.confidence) == 0.9

    # Higher confidence updates.
    await store_job_skills(
        db_session, result.job_id, [SkillMatch("Python", 1.0, "python", "tag")], skill_ids
    )
    await db_session.commit()
    # The upsert runs as a Core statement, so expire cached ORM objects before
    # re-reading to see the updated row.
    db_session.expire_all()
    row = (await db_session.execute(select(JobSkill))).scalar_one()
    assert float(row.confidence) == 1.0
    assert row.match_type == "tag"
