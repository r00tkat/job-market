"""Unit tests for software-role filtering."""

from app.services.role_filter import is_software_role


def test_keeps_obvious_software_engineering_roles():
    assert is_software_role("Senior Software Engineer", [], None)
    assert is_software_role("Backend Engineer", [], None)
    assert is_software_role("Full-Stack Engineer", [], None)
    assert is_software_role("DevOps Lead", [], None)
    assert is_software_role("Machine Learning Engineer", [], None)
    assert is_software_role("iOS Engineer", [], None)


def test_keeps_jobs_with_strong_technical_tags():
    assert is_software_role("Builder of Things", ["python", "aws"], None)
    assert is_software_role("Technical Wizard", ["kubernetes"], None)
    assert is_software_role("Generalist", ["full stack"], None)


def test_skips_non_technical_roles():
    assert not is_software_role("Marketing Manager", ["marketing"], "Run our ad campaigns")
    assert not is_software_role("Account Executive", ["sales"], "Close deals")
    assert not is_software_role("Customer Support Specialist", ["support"], "Help customers")
    assert not is_software_role("Financial Analyst", ["finance", "excel"], "Build models in Excel")


def test_weak_signals_alone_do_not_keep_records():
    # "engineer" and "dev" alone are weak; they must not keep a record.
    assert not is_software_role("Sales Engineer", ["engineer"], None)
    assert not is_software_role("Community Manager", ["dev", "digital nomad"], None)
    assert not is_software_role("Operations Lead", ["ops"], None)


def test_sre_in_title_does_not_match_inside_words():
    # "sre" must match as a token, not inside unrelated words.
    assert is_software_role("SRE", [], None)
    assert not is_software_role("Misrepresentation Analyst", [], None)
