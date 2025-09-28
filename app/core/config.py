from typing import Optional
from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # 运行环境
    app_env: str = Field(default="dev", alias="APP_ENV")

    # 方式 A：直接给完整 URL
    database_url: Optional[str] = Field(default=None, alias="DATABASE_URL")

    # 方式 B：分字段（用于 Postgres 等）
    db_user: Optional[str] = Field(default=None, alias="DB_USER")
    db_pass: Optional[str] = Field(default=None, alias="DB_PASS")
    db_name: Optional[str] = Field(default=None, alias="DB_NAME")
    db_host: Optional[str] = Field(default=None, alias="DB_HOST")
    db_port: Optional[int] = Field(default=None, alias="DB_PORT")

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",  # 忽略 .env 里未声明的键，避免报 extra_forbidden
    )

    @computed_field  # pydantic v2
    @property
    def resolved_database_url(self) -> str:
        # 优先采用完整 DATABASE_URL
        if self.database_url:
            return self.database_url

        # 其次尝试用 DB_* 拼接 Postgres URL
        if self.db_user and self.db_pass and self.db_name and self.db_host:
            port = self.db_port or 5432
            return f"postgresql+psycopg2://{self.db_user}:{self.db_pass}@{self.db_host}:{port}/{self.db_name}"

        # 兜底：本地 sqlite
        return "sqlite:///./dev.db"


settings = Settings()
