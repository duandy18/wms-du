# app/core/config.py
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    # 基本
    ENV: str = Field(default="dev")  # dev | test | prod
    DEBUG: bool = Field(default=True)

    # 数据库
    DATABASE_URL: str = Field(default="sqlite:///./dev.db")
    SQL_ECHO: bool = Field(default=False)

    # 安全/日志
    JWT_SECRET: str = Field(default="dev-temp-secret")
    LOG_LEVEL: str = Field(default="INFO")
    JSON_LOG: bool = Field(default=False)

    # 从 .env 读取，忽略多余项
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> AppSettings:
    """全局单例设置入口：from app.core.config import get_settings()."""
    return AppSettings()
