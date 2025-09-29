from typing import Optional

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",  # Ignore undeclared keys from .env to avoid extra_forbidden
    )

    database_url: Optional[str] = Field(default=None, alias="DATABASE_URL")

    DATABASE_URL: Optional[str] = None
    DB_USER: Optional[str] = None
    DB_PASS: Optional[str] = None
    DB_HOST: Optional[str] = None
    DB_PORT: Optional[int] = None
    DB_NAME: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",  # Ignore undeclared keys from .env to avoid extra_forbidden
    )

    @computed_field  # pydantic v2
    def effective_database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL  # Prefer full DATABASE_URL when provided
        if all([self.DB_USER, self.DB_PASS, self.DB_HOST, self.DB_PORT, self.DB_NAME]):
            return (
                f"postgresql+psycopg://{self.DB_USER}:{self.DB_PASS}"
                f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
            )  # Fallback: build Postgres URL from DB_* fields
        return "sqlite:///./local.db"  # Last resort: local sqlite URL


settings = Settings()
