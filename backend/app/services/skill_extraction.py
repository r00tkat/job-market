"""Skill extraction from source tags and plain-text descriptions.

Pass order (highest confidence wins per skill):
  1. tags        exact tag match               1.00  tag
  2. description contextual phrase match        0.90  contextual
  3. description explicit versioned match       0.85  versioned
  4. description exact boundary match           0.80  exact

Ambiguous short skills (Go, R, C) are never matched from generic exact prose;
they match only from tags, contextual phrases, or explicit versioned forms,
and their description patterns are case-sensitive.
"""

import re
from dataclasses import dataclass

from app.services.taxonomy import SkillDefinition

AMBIGUOUS_SHORT_SKILLS = {"go", "r", "c"}

CONFIDENCE_TAG = 1.00
CONFIDENCE_CONTEXTUAL = 0.90
CONFIDENCE_VERSIONED = 0.85
CONFIDENCE_EXACT = 0.80
MINIMUM_CONFIDENCE = 0.70

_CONTEXT_PREFIXES = [
    "experience with",
    "experience in",
    "experience using",
    "proficiency in",
    "proficiency with",
    "proficient in",
    "proficient with",
    "knowledge of",
    "expertise in",
    "expert in",
    "skilled in",
    "skilled with",
    "working with",
    "worked with",
    "background in",
    "familiarity with",
    "familiar with",
]
_PREFIX_ALTERNATION = "|".join(re.escape(prefix) for prefix in _CONTEXT_PREFIXES)


@dataclass(frozen=True)
class SkillMatch:
    canonical_name: str
    confidence: float
    matched_text: str
    match_type: str


def _boundary(term: str) -> str:
    """Non-word-neighbor boundaries; plain \\b fails for C++, Next.js, CI/CD."""
    return rf"(?<![A-Za-z0-9_]){re.escape(term)}(?![A-Za-z0-9_])"


class SkillExtractor:
    def __init__(self, taxonomy: list[SkillDefinition]) -> None:
        self._tag_lookup: dict[str, str] = {}
        self._contextual: list[tuple[str, re.Pattern[str]]] = []
        self._versioned: list[tuple[str, re.Pattern[str]]] = []
        self._exact: list[tuple[str, re.Pattern[str]]] = []

        for skill in taxonomy:
            ambiguous = skill.canonical_name.lower() in AMBIGUOUS_SHORT_SKILLS
            terms = [skill.canonical_name, *skill.aliases]
            for term in terms:
                term = term.strip()
                if not term:
                    continue
                self._tag_lookup.setdefault(term.lower(), skill.canonical_name)
                term_pattern = _boundary(term)
                if ambiguous:
                    # Case-sensitive term so prose like "go build things" never
                    # matches the Go language; the phrase prefix stays
                    # case-insensitive via a scoped inline flag.
                    contextual = re.compile(rf"(?i:{_PREFIX_ALTERNATION})\s+({term_pattern})")
                    versioned = re.compile(rf"({term_pattern})\s+v?\d+(?:\.\d+)*")
                else:
                    contextual = re.compile(
                        rf"(?:{_PREFIX_ALTERNATION})\s+({term_pattern})", re.IGNORECASE
                    )
                    versioned = re.compile(rf"({term_pattern})\s+v?\d+(?:\.\d+)*", re.IGNORECASE)
                    self._exact.append(
                        (skill.canonical_name, re.compile(f"({term_pattern})", re.IGNORECASE))
                    )
                self._contextual.append((skill.canonical_name, contextual))
                self._versioned.append((skill.canonical_name, versioned))

    def extract(self, tags: list[str] | None, description: str | None) -> list[SkillMatch]:
        """Return one match per unique skill, keeping the highest confidence."""
        best: dict[str, SkillMatch] = {}

        def consider(canonical: str, confidence: float, matched_text: str, match_type: str) -> None:
            if confidence < MINIMUM_CONFIDENCE:
                return
            current = best.get(canonical)
            if current is None or confidence > current.confidence:
                best[canonical] = SkillMatch(canonical, confidence, matched_text, match_type)

        for tag in tags or []:
            key = tag.strip().lower()
            canonical = self._tag_lookup.get(key)
            if canonical is not None:
                consider(canonical, CONFIDENCE_TAG, tag.strip(), "tag")

        text = description or ""
        if text:
            for canonical, pattern in self._contextual:
                match = pattern.search(text)
                if match:
                    consider(canonical, CONFIDENCE_CONTEXTUAL, match.group(1), "contextual")
            # Versioned matches are detected before general exact matches.
            for canonical, pattern in self._versioned:
                match = pattern.search(text)
                if match:
                    consider(canonical, CONFIDENCE_VERSIONED, match.group(0).strip(), "versioned")
            for canonical, pattern in self._exact:
                match = pattern.search(text)
                if match:
                    consider(canonical, CONFIDENCE_EXACT, match.group(1), "exact")

        return sorted(best.values(), key=lambda m: (-m.confidence, m.canonical_name))
