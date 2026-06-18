"""Application settings via pydantic-settings."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """API service configuration."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite:///./pokeapi.db"
    showdown_default_port: int = 8000
    showdown_server_dir: str = "server"
    max_concurrent_showdown: int = 4
    battle_default_timeout_s: float = 240.0
    log_level: str = "INFO"
    cors_origins: list[str] = ["*"]
    external_base_url: str = "http://localhost:8000"
    frontend_base_url: str = "http://localhost:5173"
    session_secret: str = "dev-only-change-me"  # noqa: S105
    session_cookie_name: str = "poke_battles_session"
    session_days: int = 14
    github_oauth_client_id: str | None = None
    github_oauth_client_secret: str | None = None
    google_oauth_client_id: str | None = None
    google_oauth_client_secret: str | None = None


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


__all__ = ["Settings", "get_settings"]
