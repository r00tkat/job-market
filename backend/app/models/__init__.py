"""ORM models. Importing this package registers all tables on Base.metadata."""

from app.db.base import Base
from app.models.company import Company
from app.models.dedup_decision import DedupDecision
from app.models.job import Job
from app.models.job_skill import JobSkill
from app.models.scrape_run import ScrapeRun
from app.models.skill import Skill

__all__ = [
    "Base",
    "Company",
    "DedupDecision",
    "Job",
    "JobSkill",
    "ScrapeRun",
    "Skill",
]
