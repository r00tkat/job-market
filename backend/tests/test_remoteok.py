"""Unit tests for the RemoteOK source adapter (HTTP mocked, never real calls)."""

import httpx
import pytest
from pydantic import ValidationError

from app.sources.base import RateLimitError, SourceError
from app.sources.remoteok import (
    REMOTEOK_API_URL,
    RawRemoteOKJob,
    fetch_raw_records,
    is_metadata_record,
    resolve_source_url,
    strip_metadata,
)

METADATA = {"legal": "RemoteOK API legal notice", "last_updated": 1781172000}

VALID_JOB = {
    "id": 100,
    "slug": "backend-engineer-acme-100",
    "company": "Acme",
    "position": "Backend Engineer",
    "description": "<p>Build APIs with Python</p>",
    "tags": ["python", "backend"],
    "location": "Worldwide",
    "salary_min": 90000,
    "salary_max": 120000,
    "date": "2026-06-10T10:00:00+00:00",
    "epoch": 1781172000,
    "url": "https://remoteok.com/remote-jobs/backend-engineer-acme-100",
}


def test_metadata_element_is_skipped():
    assert is_metadata_record(METADATA)
    assert not is_metadata_record(VALID_JOB)
    records = strip_metadata([METADATA, VALID_JOB])
    assert records == [VALID_JOB]


def test_valid_job_is_parsed():
    raw = RawRemoteOKJob.model_validate(VALID_JOB)
    assert raw.position == "Backend Engineer"
    assert raw.company == "Acme"
    assert raw.tags == ["python", "backend"]
    assert raw.salary_min == 90000


def test_unknown_fields_do_not_break_parsing():
    payload = dict(VALID_JOB, totally_new_field={"nested": True})
    raw = RawRemoteOKJob.model_validate(payload)
    assert raw.position == "Backend Engineer"


def test_invalid_record_raises_validation_error():
    with pytest.raises(ValidationError):
        RawRemoteOKJob.model_validate({"id": 1, "position": 12345, "company": "Acme"})


def test_source_url_prefers_absolute_remoteok_url():
    raw = RawRemoteOKJob.model_validate(VALID_JOB)
    assert resolve_source_url(raw) == "https://remoteok.com/remote-jobs/backend-engineer-acme-100"


def test_source_url_falls_back_to_slug_then_id():
    raw = RawRemoteOKJob.model_validate(dict(VALID_JOB, url="https://example.com/elsewhere"))
    assert resolve_source_url(raw) == "https://remoteok.com/remote-jobs/backend-engineer-acme-100"
    raw = RawRemoteOKJob.model_validate(dict(VALID_JOB, url=None, slug=None))
    assert resolve_source_url(raw) == "https://remoteok.com/remote-jobs/100"


def test_missing_stable_source_url_returns_none():
    raw = RawRemoteOKJob.model_validate(
        {"company": "Acme", "position": "Backend Engineer", "url": "https://example.com/job"}
    )
    assert resolve_source_url(raw) is None


async def test_fetch_returns_records(httpx_mock):
    httpx_mock.add_response(url=REMOTEOK_API_URL, json=[METADATA, VALID_JOB])
    records = await fetch_raw_records()
    assert records == [METADATA, VALID_JOB]


async def test_http_429_raises_rate_limit_error(httpx_mock):
    httpx_mock.add_response(url=REMOTEOK_API_URL, status_code=429)
    with pytest.raises(RateLimitError):
        await fetch_raw_records()


async def test_non_2xx_raises_source_error(httpx_mock):
    httpx_mock.add_response(url=REMOTEOK_API_URL, status_code=500)
    with pytest.raises(SourceError):
        await fetch_raw_records()


async def test_timeout_raises_source_error(httpx_mock):
    httpx_mock.add_exception(httpx.ReadTimeout("timed out"))
    with pytest.raises(SourceError):
        await fetch_raw_records()


async def test_non_array_payload_raises_source_error(httpx_mock):
    httpx_mock.add_response(url=REMOTEOK_API_URL, json={"error": "nope"})
    with pytest.raises(SourceError):
        await fetch_raw_records()
