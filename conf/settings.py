from __future__ import annotations

from pydantic_settings import BaseSettings
from pydantic import Field, AnyHttpUrl, EmailStr
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    # Casdoor OAuth
    CASDOOR_ENDPOINT: str | None = None
    CASDOOR_CLIENT_ID: str | None = None
    CASDOOR_CLIENT_SECRET: str | None = None
    CASDOOR_ORG_NAME: str | None = None
    CASDOOR_APP_NAME: str | None = None
    CASDOOR_CERT_PATH: str | None = None

    # n8n integration
    N8N_BASE_URL: AnyHttpUrl
    N8N_DB_DSN: str  # e.g., postgresql+asyncpg://user:pass@host:5432/n8n
    
    # Optional: owner creds ONLY for REST /rest/login when we need to create a "browser" cookie
    N8N_OWNER_EMAIL: Optional[EmailStr] = None
    N8N_OWNER_PASSWORD: Optional[str] = None

    # Defaults for new users/projects
    N8N_DEFAULT_GLOBAL_ROLE: str = "global:member"
    N8N_DEFAULT_PROJECT_ROLE: str = "project:personalOwner"
    N8N_DEFAULT_LOCALE: str = "en"

    # Security / cookies
    COOKIE_SECURE: bool = True
    SECRET_KEY: str | None = None

    class Config:
        case_sensitive = True
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "allow"


@lru_cache
def get_settings() -> Settings:  # pragma: no cover
    return Settings()  # type: ignore[arg-type]
