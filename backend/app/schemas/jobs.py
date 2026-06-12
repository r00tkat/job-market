"""Response schemas for GET /jobs."""

import uuid

from pydantic import BaseModel

from app.schemas.common import UtcDatetime


class CompanyOut(BaseModel):
    id: uuid.UUID
    name: str
    website: str | None


class JobSkillOut(BaseModel):
    canonical_name: str
    category: str
    confidence: float


class JobOut(BaseModel):
    id: uuid.UUID
    title: str
    company: CompanyOut
    location: str | None
    remote_type: str
    employment_type: str
    salary_min: int | None
    salary_max: int | None
    salary_currency: str | None
    source: str
    source_url: str
    posted_at: UtcDatetime | None
    collected_at: UtcDatetime
    skills: list[JobSkillOut]


class JobsResponse(BaseModel):
    items: list[JobOut]
    total: int
    limit: int
    offset: int
