"""RemoteOK public API source adapter.

Compliance notes (see SOURCE_COMPLIANCE.md): the original RemoteOK URL is
stored with every job, public display of RemoteOK-derived jobs must credit
RemoteOK and link back to the original posting, and the RemoteOK logo must not
be used without explicit permission.
"""

from typing import Any

import httpx
import structlog
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.config import get_settings
from app.sources.base import RateLimitError, SourceError

REMOTEOK_API_URL = "https://remoteok.com/api"

log = structlog.get_logger("sources.remoteok")


class RawRemoteOKJob(BaseModel):
    """Permissive model for one raw RemoteOK record. Unknown fields are ignored."""

    model_config = ConfigDict(extra="ignore")

    id: int | str | None = None
    slug: str | None = None
    company: str | None = None
    position: str | None = None
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    location: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    date: str | None = None
    epoch: int | float | str | None = None
    url: str | None = None
    apply_url: str | None = None

    @field_validator("salary_min", "salary_max", mode="before")
    @classmethod
    def _coerce_salary(cls, value: Any) -> int | None:
        """Coerce salary values defensively; zero and junk become None."""
        if value in (None, "", 0, "0"):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @field_validator("tags", mode="before")
    @classmethod
    def _coerce_tags(cls, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, str)]


def is_metadata_record(record: dict[str, Any]) -> bool:
    """The first element of the RemoteOK payload is legal metadata, not a job."""
    if "legal" in record:
        return True
    return not any(record.get(key) for key in ("position", "company", "slug", "id"))


def strip_metadata(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if records and is_metadata_record(records[0]):
        return records[1:]
    return records


def resolve_source_url(raw: RawRemoteOKJob) -> str | None:
    """Resolve a stable RemoteOK URL, or None if no stable URL can be produced."""
    url = (raw.url or "").strip()
    if url.lower().startswith("https://remoteok.com/"):
        return url
    if raw.slug:
        return f"https://remoteok.com/remote-jobs/{raw.slug}"
    if raw.id is not None and str(raw.id).strip():
        return f"https://remoteok.com/remote-jobs/{raw.id}"
    return None


async def fetch_raw_records() -> list[dict[str, Any]]:
    """Fetch the RemoteOK API and return the raw list of dict records.

    Raises RateLimitError on HTTP 429 and SourceError on timeouts, transport
    failures, other non-2xx responses, and malformed payloads.
    """
    settings = get_settings()
    headers = {
        "Accept": "application/json",
        "User-Agent": settings.remoteok_user_agent,
    }
    try:
        async with httpx.AsyncClient(
            timeout=settings.scrape_timeout_seconds,
            headers=headers,
            follow_redirects=True,
        ) as client:
            response = await client.get(REMOTEOK_API_URL)
    except httpx.TimeoutException as exc:
        raise SourceError(f"RemoteOK request timed out: {exc}") from exc
    except httpx.HTTPError as exc:
        raise SourceError(f"RemoteOK request failed: {exc}") from exc

    if response.status_code == 429:
        raise RateLimitError("RemoteOK rate-limited the request (HTTP 429)")
    if not (200 <= response.status_code < 300):
        raise SourceError(f"RemoteOK returned HTTP {response.status_code}")

    try:
        data = response.json()
    except ValueError as exc:
        raise SourceError("RemoteOK returned a non-JSON response") from exc
    if not isinstance(data, list):
        raise SourceError("RemoteOK API did not return a JSON array")

    return [record for record in data if isinstance(record, dict)]
