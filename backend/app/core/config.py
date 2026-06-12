"""Centralized application configuration via pydantic-settings."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from the environment and an optional .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: Literal["local", "test", "production"] = "local"
    database_url: str | None = None
    test_database_url: str | None = None
    log_level: str = "info"
    scrape_timeout_seconds: float = 30.0
    freshness_threshold_hours: int = 25
    remoteok_user_agent: str = "job-market-intelligence/1.0"

    @property
    def effective_database_url(self) -> str:
        """Resolve the database URL for the current environment.

        In ENV=test, TEST_DATABASE_URL is used exclusively; tests never fall
        back to production credentials. Outside tests, DATABASE_URL is required.
        """
        if self.env == "test":
            if not self.test_database_url:
                raise RuntimeError(
                    "TEST_DATABASE_URL is required when ENV=test; "
                    "tests never fall back to DATABASE_URL."
                )
            return self.test_database_url
        if not self.database_url:
            raise RuntimeError("DATABASE_URL is required outside tests.")
        return self.database_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
