"""Content hashing for deduplication."""

import hashlib
import re

_WHITESPACE_RE = re.compile(r"\s+")


def compute_content_hash(title: str, company_name: str, description_text: str) -> str:
    """SHA-256 hex digest of normalized title, company name, and plain-text description.

    The three parts are joined with newlines, lowercased, whitespace-collapsed,
    and UTF-8 encoded before hashing. Raw HTML and raw payloads are never hashed.
    """
    raw = "\n".join([title or "", company_name or "", description_text or ""])
    normalized = _WHITESPACE_RE.sub(" ", raw.lower()).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
