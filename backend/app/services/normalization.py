"""Normalization of raw RemoteOK records into persistable values."""

import re
from datetime import UTC, datetime
from typing import Any

from bs4 import BeautifulSoup
from pydantic import BaseModel

from app.core.hashing import compute_content_hash
from app.sources.remoteok import RawRemoteOKJob

_WHITESPACE_RE = re.compile(r"\s+")
_INLINE_WHITESPACE_RE = re.compile(r"[ \t]+")
_PUNCT_RE = re.compile(r"[^\w\s-]")

# Sanity bounds for epoch values: 2000-01-01 .. 2100-01-01 (UTC).
_EPOCH_MIN = 946684800
_EPOCH_MAX = 4102444800


class NormalizedJob(BaseModel):
    """A fully normalized job record, ready for persistence."""

    title: str
    company_name: str
    company_normalized_name: str
    location: str | None
    employment_type: str
    salary_min: int | None
    salary_max: int | None
    salary_currency: str | None
    remote_type: str
    description: str | None
    description_html: str | None
    source: str
    source_id: str | None
    source_url: str
    posted_at: datetime | None
    tags: list[str]
    content_hash: str
    raw_payload: dict[str, Any]


def clean_text(value: str | None) -> str:
    """Strip leading/trailing whitespace and collapse repeated whitespace."""
    if not value:
        return ""
    return _WHITESPACE_RE.sub(" ", value).strip()


def normalize_company_name(name: str) -> str:
    """Lowercase, strip punctuation except hyphens, and collapse whitespace."""
    lowered = name.lower()
    no_punct = _PUNCT_RE.sub(" ", lowered)
    return _WHITESPACE_RE.sub(" ", no_punct).strip()


def html_to_text(html: str | None) -> str:
    """Extract plain text from HTML, preserving block separation with newlines."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator="\n")
    lines = [_INLINE_WHITESPACE_RE.sub(" ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def normalize_salary(value: int | None) -> int | None:
    """Salary 0 (and negative junk) is stored as None."""
    if value is None or value <= 0:
        return None
    return value


def parse_posted_at(date_str: str | None, epoch: int | float | str | None) -> datetime | None:
    """Parse to a timezone-aware UTC datetime; prefer epoch when valid."""
    epoch_dt: datetime | None = None
    if epoch is not None:
        try:
            value = float(epoch)
            if _EPOCH_MIN <= value <= _EPOCH_MAX:
                epoch_dt = datetime.fromtimestamp(value, tz=UTC)
        except (TypeError, ValueError, OSError, OverflowError):
            epoch_dt = None

    date_dt: datetime | None = None
    if date_str:
        try:
            parsed = datetime.fromisoformat(str(date_str).replace("Z", "+00:00"))
            date_dt = parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
            date_dt = date_dt.astimezone(UTC)
        except ValueError:
            date_dt = None

    return epoch_dt or date_dt


def classify_remote_type(tags: list[str], location: str | None, description: str | None) -> str:
    """RemoteOK is a remote-job board: default to remote unless evidence says otherwise."""
    text = " ".join([*(tags or []), location or "", description or ""]).lower()
    if "hybrid" in text:
        return "hybrid"
    if "on-site" in text or "onsite" in text:
        return "onsite"
    return "remote"


def classify_employment_type(tags: list[str], title: str, description: str | None) -> str:
    """Map obvious employment-type signals; use 'unknown' when ambiguous."""
    tag_set = {tag.lower() for tag in tags or []}
    text = " ".join([title or "", description or ""]).lower()
    if tag_set & {"internship", "intern"} or "internship" in text:
        return "internship"
    if tag_set & {"part-time", "part time", "part_time"} or "part-time" in text:
        return "part_time"
    if tag_set & {"contract", "contractor", "freelance"} or "contractor" in text:
        return "contract"
    full_time_signals = "full-time" in text or "full time" in text
    if tag_set & {"full-time", "full time", "full_time"} or full_time_signals:
        return "full_time"
    return "unknown"


def normalize_record(
    raw: RawRemoteOKJob, source_url: str, raw_payload: dict[str, Any]
) -> NormalizedJob:
    """Build a NormalizedJob from a validated raw record and its resolved URL."""
    title = clean_text(raw.position)
    company_name = clean_text(raw.company)
    tags = [clean_text(tag).lower() for tag in raw.tags or [] if clean_text(tag)]
    description_html = raw.description.strip() if raw.description else None
    description = html_to_text(raw.description) or None
    salary_min = normalize_salary(raw.salary_min)
    salary_max = normalize_salary(raw.salary_max)
    salary_currency = "USD" if (salary_min is not None or salary_max is not None) else None
    location = clean_text(raw.location) or None

    return NormalizedJob(
        title=title,
        company_name=company_name,
        company_normalized_name=normalize_company_name(company_name),
        location=location,
        employment_type=classify_employment_type(tags, title, description),
        salary_min=salary_min,
        salary_max=salary_max,
        salary_currency=salary_currency,
        remote_type=classify_remote_type(tags, location, description),
        description=description,
        description_html=description_html,
        source="remoteok",
        source_id=str(raw.id) if raw.id is not None else None,
        source_url=source_url,
        posted_at=parse_posted_at(raw.date, raw.epoch),
        tags=tags,
        content_hash=compute_content_hash(title, company_name, description or ""),
        raw_payload=raw_payload,
    )
