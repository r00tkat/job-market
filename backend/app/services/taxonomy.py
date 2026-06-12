"""Skill taxonomy loading and seeding.

The taxonomy lives in data/skills.json. Editing that file is enough to add a
new skill; no skill names are hardcoded in Python source.
"""

import json
import uuid
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Skill

SkillCategory = Literal[
    "languages",
    "frameworks",
    "cloud",
    "databases",
    "infrastructure",
    "data",
    "ml_adjacent",
]

# Resolves to backend/data/skills.json in a checkout or editable install.
_MODULE_RELATIVE_PATH = Path(__file__).resolve().parents[2] / "data" / "skills.json"


class SkillDefinition(BaseModel):
    canonical_name: str
    category: SkillCategory
    aliases: list[str] = Field(default_factory=list)


def default_taxonomy_path() -> Path:
    if _MODULE_RELATIVE_PATH.exists():
        return _MODULE_RELATIVE_PATH
    # Non-editable installs (e.g. Docker) run from a working directory that
    # contains data/skills.json.
    return Path.cwd() / "data" / "skills.json"


def load_taxonomy(path: Path | None = None) -> list[SkillDefinition]:
    taxonomy_path = path or default_taxonomy_path()
    raw = json.loads(taxonomy_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("skills.json must contain a JSON array")
    return [SkillDefinition.model_validate(item) for item in raw]


async def seed_skills(
    session: AsyncSession, taxonomy: list[SkillDefinition]
) -> dict[str, uuid.UUID]:
    """Upsert the skills table from the taxonomy; returns canonical_name -> id."""
    skill_ids: dict[str, uuid.UUID] = {}
    for definition in taxonomy:
        aliases = sorted({alias.strip().lower() for alias in definition.aliases if alias.strip()})
        stmt = (
            pg_insert(Skill)
            .values(
                id=uuid.uuid4(),
                canonical_name=definition.canonical_name,
                category=definition.category,
                aliases=aliases,
            )
            .on_conflict_do_update(
                index_elements=["canonical_name"],
                set_={"category": definition.category, "aliases": aliases},
            )
            .returning(Skill.id)
        )
        result = await session.execute(stmt)
        skill_ids[definition.canonical_name] = result.scalar_one()
    return skill_ids
