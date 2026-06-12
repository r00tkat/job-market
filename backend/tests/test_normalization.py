"""Unit tests for normalization."""

from app.core.hashing import compute_content_hash
from app.services.normalization import (
    classify_remote_type,
    clean_text,
    html_to_text,
    normalize_company_name,
    normalize_record,
    normalize_salary,
)
from app.sources.remoteok import RawRemoteOKJob


def _raw(**overrides):
    base = {
        "id": 1,
        "slug": "backend-engineer-1",
        "company": "Acme Corp",
        "position": "Backend Engineer",
        "description": "<p>Build APIs with <b>Python</b></p>",
        "tags": ["python", "backend"],
        "location": "Worldwide",
        "salary_min": 0,
        "salary_max": 0,
        "date": "2026-06-10T10:00:00+00:00",
        "epoch": 1781172000,
        "url": "https://remoteok.com/remote-jobs/backend-engineer-1",
    }
    base.update(overrides)
    return RawRemoteOKJob.model_validate(base)


def test_clean_text_trims_and_collapses_whitespace():
    assert clean_text("  Senior   Backend\t Engineer \n") == "Senior Backend Engineer"


def test_html_to_text_preserves_block_separation():
    text = html_to_text("<p>First paragraph</p><ul><li>Item one</li><li>Item two</li></ul>")
    assert "First paragraph" in text
    assert "Item one" in text
    assert "\n" in text
    assert "<" not in text


def test_html_is_stripped_from_description():
    record = normalize_record(_raw(), "https://remoteok.com/remote-jobs/x", {})
    assert record.description == "Build APIs with\nPython" or "Python" in record.description
    assert "<p>" not in (record.description or "")
    assert "<b>" not in (record.description or "")


def test_html_preserved_in_description_html():
    record = normalize_record(_raw(), "https://remoteok.com/remote-jobs/x", {})
    assert record.description_html is not None
    assert "<p>" in record.description_html
    assert "<b>" in record.description_html


def test_salary_zero_becomes_none():
    assert normalize_salary(0) is None
    assert normalize_salary(-10) is None
    assert normalize_salary(120000) == 120000
    record = normalize_record(_raw(salary_min=0, salary_max=0), "https://remoteok.com/x", {})
    assert record.salary_min is None
    assert record.salary_max is None
    assert record.salary_currency is None


def test_salary_currency_set_when_salary_present():
    record = normalize_record(_raw(salary_min=100000), "https://remoteok.com/x", {})
    assert record.salary_min == 100000
    assert record.salary_currency == "USD"


def test_remoteok_defaults_to_remote():
    assert classify_remote_type(["python"], "Worldwide", "Build things") == "remote"


def test_hybrid_overrides_remote_default():
    assert classify_remote_type([], None, "This is a hybrid role in Berlin") == "hybrid"


def test_onsite_overrides_remote_default():
    assert classify_remote_type([], "On-site NYC", None) == "onsite"
    assert classify_remote_type(["onsite"], None, None) == "onsite"


def test_company_display_name_preserved():
    record = normalize_record(_raw(company="  OpenAI  "), "https://remoteok.com/x", {})
    assert record.company_name == "OpenAI"  # source casing preserved, whitespace cleaned


def test_company_normalized_name_generation():
    assert normalize_company_name("Acme, Inc.") == "acme inc"
    assert normalize_company_name("  Foo   Bar  ") == "foo bar"
    assert normalize_company_name("E-Corp!") == "e-corp"  # hyphens kept


def test_content_hash_changes_when_company_changes():
    hash_a = compute_content_hash("Backend Engineer", "Acme", "Build APIs")
    hash_b = compute_content_hash("Backend Engineer", "Globex", "Build APIs")
    assert hash_a != hash_b


def test_content_hash_stable_under_whitespace_and_case():
    hash_a = compute_content_hash("Backend Engineer", "Acme", "Build  APIs")
    hash_b = compute_content_hash("backend engineer", "ACME", "build apis")
    assert hash_a == hash_b


def test_posted_at_prefers_epoch():
    record = normalize_record(
        _raw(date="2026-06-01T00:00:00+00:00", epoch=1781172000),
        "https://remoteok.com/x",
        {},
    )
    assert record.posted_at is not None
    assert record.posted_at.timestamp() == 1781172000


def test_posted_at_none_when_both_invalid():
    record = normalize_record(_raw(date="not-a-date", epoch="junk"), "https://remoteok.com/x", {})
    assert record.posted_at is None
