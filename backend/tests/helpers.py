"""Shared test helpers for building normalized records and database rows."""

import uuid
from datetime import UTC, datetime
from typing import Any

from app.core.hashing import compute_content_hash
from app.models import Job
from app.services.normalization import NormalizedJob, normalize_company_name


def make_normalized(**overrides: Any) -> NormalizedJob:
    title = overrides.pop("title", "Backend Engineer")
    company_name = overrides.pop("company_name", "Acme")
    description = overrides.pop("description", "Build APIs with Python")
    base: dict[str, Any] = {
        "title": title,
        "company_name": company_name,
        "company_normalized_name": normalize_company_name(company_name),
        "location": "Remote",
        "employment_type": "full_time",
        "salary_min": None,
        "salary_max": None,
        "salary_currency": None,
        "remote_type": "remote",
        "description": description,
        "description_html": f"<p>{description}</p>",
        "source": "remoteok",
        "source_id": "1",
        "source_url": "https://remoteok.com/remote-jobs/backend-1",
        "posted_at": None,
        "tags": ["python"],
        "content_hash": compute_content_hash(title, company_name, description),
        "raw_payload": {},
    }
    base.update(overrides)
    if "content_hash" not in overrides:
        base["content_hash"] = compute_content_hash(
            base["title"], base["company_name"], base["description"] or ""
        )
    return NormalizedJob(**base)


def make_job(company_id: uuid.UUID, **overrides: Any) -> Job:
    now = datetime.now(UTC)
    title = overrides.pop("title", "Backend Engineer")
    description = overrides.pop("description", "Build APIs")
    values: dict[str, Any] = {
        "id": uuid.uuid4(),
        "company_id": company_id,
        "title": title,
        "location": "Remote",
        "employment_type": "full_time",
        "remote_type": "remote",
        "description": description,
        "description_html": f"<p>{description}</p>",
        "source": "remoteok",
        "source_id": str(uuid.uuid4())[:8],
        "source_url": f"https://remoteok.com/remote-jobs/{uuid.uuid4()}",
        "posted_at": now,
        "collected_at": now,
        "last_seen_at": now,
        "content_hash": compute_content_hash(title, "Acme", description),
        "raw_payload": {},
        "is_duplicate": False,
        "canonical_id": None,
        "created_at": now,
        "updated_at": now,
    }
    values.update(overrides)
    return Job(**values)
