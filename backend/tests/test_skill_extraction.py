"""Unit tests for skill extraction, using the real shipped taxonomy."""

import json

import pytest

from app.services.skill_extraction import SkillExtractor
from app.services.taxonomy import load_taxonomy


@pytest.fixture(scope="module")
def extractor() -> SkillExtractor:
    return SkillExtractor(load_taxonomy())


def _by_name(matches):
    return {m.canonical_name: m for m in matches}


def test_tag_match_returns_confidence_1(extractor):
    matches = _by_name(extractor.extract(["python"], None))
    assert matches["Python"].confidence == 1.0
    assert matches["Python"].match_type == "tag"


def test_contextual_match_returns_confidence_09(extractor):
    matches = _by_name(extractor.extract([], "We want experience with Python for this role."))
    assert matches["Python"].confidence == 0.9
    assert matches["Python"].match_type == "contextual"


def test_versioned_match_returns_confidence_085(extractor):
    matches = _by_name(extractor.extract([], "Our stack runs Python 3.12 in production."))
    assert matches["Python"].confidence == 0.85
    assert matches["Python"].match_type == "versioned"
    assert "Python 3.12" in matches["Python"].matched_text


def test_exact_description_match_returns_confidence_08(extractor):
    matches = _by_name(extractor.extract([], "We deploy Terraform daily."))
    assert matches["Terraform"].confidence == 0.8
    assert matches["Terraform"].match_type == "exact"


def test_aliases_map_to_canonical_skills(extractor):
    matches = _by_name(extractor.extract(["k8s", "golang", "postgres"], None))
    assert "Kubernetes" in matches
    assert "Go" in matches
    assert "PostgreSQL" in matches


def test_tricky_terms_match_correctly(extractor):
    text = "Stack: C++ services, a Next.js frontend, CI/CD pipelines, and scikit-learn models."
    matches = _by_name(extractor.extract([], text))
    assert "C++" in matches
    assert "Next.js" in matches
    assert "CI/CD" in matches
    assert "scikit-learn" in matches


def test_bare_prose_go_does_not_match(extractor):
    matches = _by_name(extractor.extract([], "We go build things together and go far."))
    assert "Go" not in matches


def test_contextual_go_matches(extractor):
    matches = _by_name(extractor.extract([], "You have experience with Go and Rust."))
    assert "Go" in matches
    assert matches["Go"].match_type == "contextual"


def test_versioned_examples(extractor):
    matches = _by_name(extractor.extract([], "React 18 and Node.js v20 and PostgreSQL 16."))
    assert matches["React"].match_type == "versioned"
    assert matches["JavaScript"].match_type == "versioned"  # node.js alias
    assert matches["PostgreSQL"].match_type == "versioned"


def test_highest_confidence_wins(extractor):
    matches = _by_name(
        extractor.extract(["python"], "We want experience with Python 3.12 every day.")
    )
    assert matches["Python"].confidence == 1.0
    assert matches["Python"].match_type == "tag"


def test_one_match_per_unique_skill(extractor):
    matches = extractor.extract([], "Python here. experience with Python. Python 3.12.")
    names = [m.canonical_name for m in matches]
    assert names.count("Python") == 1


def test_adding_skill_to_json_changes_extraction(tmp_path):
    taxonomy_file = tmp_path / "skills.json"
    taxonomy_file.write_text(
        json.dumps(
            [
                {
                    "canonical_name": "Zig",
                    "category": "languages",
                    "aliases": ["ziglang"],
                }
            ]
        ),
        encoding="utf-8",
    )
    extractor = SkillExtractor(load_taxonomy(taxonomy_file))
    matches = _by_name(extractor.extract(["ziglang"], "We also use Zig in production."))
    assert "Zig" in matches
    assert matches["Zig"].confidence == 1.0
