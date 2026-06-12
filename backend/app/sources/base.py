"""Source adapter error types."""


class SourceError(Exception):
    """The source could not be fetched or returned an unusable response."""


class RateLimitError(SourceError):
    """The source rate-limited the request (HTTP 429)."""
