"""Initial schema: companies, jobs, skills, job_skills, scrape_runs, dedup_decisions.

Revision ID: 0001
Revises:
Create Date: 2026-06-12

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("normalized_name", sa.Text(), nullable=False),
        sa.Column("website", sa.Text(), nullable=True),
        sa.Column("industry", sa.Text(), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("idx_companies_normalized_name", "companies", ["normalized_name"], unique=True)

    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id"),
            nullable=False,
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column(
            "employment_type", sa.Text(), nullable=False, server_default=sa.text("'unknown'")
        ),
        sa.Column("salary_min", sa.Integer(), nullable=True),
        sa.Column("salary_max", sa.Integer(), nullable=True),
        sa.Column("salary_currency", sa.Text(), nullable=True),
        sa.Column("remote_type", sa.Text(), nullable=False, server_default=sa.text("'unknown'")),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("description_html", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("posted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "collected_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=True),
        sa.Column("is_duplicate", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "canonical_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("jobs.id"), nullable=True
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("idx_jobs_source_url", "jobs", ["source_url"], unique=True)
    op.create_index("idx_jobs_content_hash", "jobs", ["content_hash"])
    op.create_index(
        "idx_jobs_not_duplicate",
        "jobs",
        ["is_duplicate"],
        postgresql_where=sa.text("is_duplicate = false"),
    )
    op.create_index("idx_jobs_collected_at", "jobs", [sa.text("collected_at DESC")])
    op.create_index("idx_jobs_posted_at", "jobs", [sa.text("posted_at DESC")])
    op.create_index("idx_jobs_company_posted_at", "jobs", ["company_id", sa.text("posted_at DESC")])
    op.create_index("idx_jobs_source_posted_at", "jobs", ["source", sa.text("posted_at DESC")])

    op.create_table(
        "skills",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("canonical_name", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column(
            "aliases", postgresql.ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'")
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("canonical_name", name="uq_skills_canonical_name"),
    )

    op.create_table(
        "job_skills",
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "skill_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("skills.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("confidence", sa.Numeric(3, 2), nullable=False),
        sa.Column("matched_text", sa.Text(), nullable=False),
        sa.Column("match_type", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0", name="ck_job_skills_confidence"
        ),
    )
    op.create_index("idx_job_skills_skill_id", "job_skills", ["skill_id"])

    op.create_table(
        "scrape_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "started_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("records_seen", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("records_skipped", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("jobs_inserted", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("jobs_updated", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("duplicates_found", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index(
        "idx_scrape_runs_source_started_at",
        "scrape_runs",
        ["source", sa.text("started_at DESC")],
    )

    op.create_table(
        "dedup_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("incoming_source", sa.Text(), nullable=False),
        sa.Column("incoming_source_url", sa.Text(), nullable=False),
        sa.Column(
            "matched_job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("jobs.id"),
            nullable=True,
        ),
        sa.Column("pass_name", sa.Text(), nullable=False),
        sa.Column("match_signal", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("dedup_decisions")
    op.drop_index("idx_scrape_runs_source_started_at", table_name="scrape_runs")
    op.drop_table("scrape_runs")
    op.drop_index("idx_job_skills_skill_id", table_name="job_skills")
    op.drop_table("job_skills")
    op.drop_table("skills")
    op.drop_index("idx_jobs_source_posted_at", table_name="jobs")
    op.drop_index("idx_jobs_company_posted_at", table_name="jobs")
    op.drop_index("idx_jobs_posted_at", table_name="jobs")
    op.drop_index("idx_jobs_collected_at", table_name="jobs")
    op.drop_index("idx_jobs_not_duplicate", table_name="jobs")
    op.drop_index("idx_jobs_content_hash", table_name="jobs")
    op.drop_index("idx_jobs_source_url", table_name="jobs")
    op.drop_table("jobs")
    op.drop_index("idx_companies_normalized_name", table_name="companies")
    op.drop_table("companies")
