# app/core/config.py
from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """
    全局应用配置（统一使用 PostgreSQL，不再允许 fallback 到 sqlite）
    """

    # 运行环境
    ENV: str = Field(default="dev")
    DEBUG: bool = Field(default=True)

    # 数据库 —— 这里强制要求必须从环境变量或 .env 文件读取
    DATABASE_URL: str = Field(
        default=...,
        description="PostgreSQL 连接串，例如：postgresql+psycopg://wms:wms@127.0.0.1:5435/wms",
    )
    SQL_ECHO: bool = Field(default=False)

    # 安全 / 日志
    JWT_SECRET: str = Field(default="dev-temp-secret")
    LOG_LEVEL: str = Field(default="INFO")
    JSON_LOG: bool = Field(default=False)

    # 出库策略
    ALLOW_SHIP_WITHOUT_RESERVE: bool = Field(default=True)

    # 允许从 .env 文件读取配置
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> AppSettings:
    """全局单例设置入口。"""
    return AppSettings()
