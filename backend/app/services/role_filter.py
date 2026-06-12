"""Software-engineering role filtering.

Applied after normalization and before database writes. False positives
pollute the analytics more than false negatives in Phase 1, so uncertain
records are skipped.
"""

import re

STRONG_TITLE_SIGNALS = [
    "software engineer",
    "backend engineer",
    "frontend engineer",
    "full stack engineer",
    "full-stack engineer",
    "developer",
    "devops",
    "site reliability",
    "sre",
    "platform engineer",
    "infrastructure engineer",
    "data engineer",
    "machine learning engineer",
    "ml engineer",
    "ai engineer",
    "mobile engineer",
    "ios engineer",
    "android engineer",
    "security engineer",
    "qa automation",
    "test automation",
]

STRONG_TAG_SIGNALS = {
    "python",
    "javascript",
    "typescript",
    "go",
    "golang",
    "rust",
    "java",
    "c++",
    "react",
    "next.js",
    "django",
    "fastapi",
    "aws",
    "gcp",
    "azure",
    "kubernetes",
    "docker",
    "terraform",
    "postgres",
    "postgresql",
    "redis",
    "kafka",
    "spark",
    "devops",
    "backend",
    "frontend",
    "full stack",
    "web dev",
    "mobile dev",
    "data engineer",
    "machine learning",
}

# Weak signals such as "engineer", "dev", "digital nomad", "ops", "marketing",
# "finance", "excel", "support" are deliberately NOT in the lists above: they
# must never keep a record on their own.


def _compile_signal(phrase: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![a-z0-9_]){re.escape(phrase)}(?![a-z0-9_])")


_TITLE_PATTERNS = [_compile_signal(phrase) for phrase in STRONG_TITLE_SIGNALS]
# For descriptions, only multi-word signals are used: single words like
# "developer" appearing somewhere in prose are too weak on their own.
_DESCRIPTION_PATTERNS = [
    _compile_signal(phrase) for phrase in STRONG_TITLE_SIGNALS if " " in phrase or "-" in phrase
]


def is_software_role(title: str, tags: list[str], description: str | None) -> bool:
    """Keep a record only if it has a strong software-engineering signal."""
    title_lower = (title or "").lower()
    if any(pattern.search(title_lower) for pattern in _TITLE_PATTERNS):
        return True

    tag_set = {tag.strip().lower() for tag in tags or []}
    if tag_set & STRONG_TAG_SIGNALS:
        return True

    description_lower = (description or "").lower()
    if description_lower and any(
        pattern.search(description_lower) for pattern in _DESCRIPTION_PATTERNS
    ):
        return True

    return False
