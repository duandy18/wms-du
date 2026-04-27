# Module split: platform order ingestion now owns platform app config, auth, connection checks, native pull/ingest, and native order ledgers; no legacy alias is kept.
# app/platform_order_ingestion/jd/settings.py
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping, Optional

from app.platform_order_ingestion.models.jd_app_config import JdAppConfig

from .errors import JdJosConfigError


DEFAULT_JD_GATEWAY_URL = "https://api.jd.com/routerjson"
DEFAULT_JD_API_VERSION = "2.0"
DEFAULT_JD_SIGN_METHOD = "md5"


@dataclass(frozen=True)
class JdJosConfig:
    """
    OMS 京东 / JOS 协议配置。

    第一阶段职责：
    - 只承载协议发送所需的最小配置
    - 不承载授权状态
    - 不承载店铺业务语义
    """

    client_id: str
    client_secret: str
    gateway_url: str = DEFAULT_JD_GATEWAY_URL
    version: str = DEFAULT_JD_API_VERSION
    sign_method: str = DEFAULT_JD_SIGN_METHOD

    @classmethod
    def from_mapping(
        cls,
        data: Mapping[str, object],
    ) -> "JdJosConfig":
        client_id = str(data.get("client_id") or "").strip()
        client_secret = str(data.get("client_secret") or "").strip()
        gateway_url = str(data.get("gateway_url") or DEFAULT_JD_GATEWAY_URL).strip()
        version = str(data.get("version") or DEFAULT_JD_API_VERSION).strip()
        sign_method = str(data.get("sign_method") or DEFAULT_JD_SIGN_METHOD).strip().lower()

        cfg = cls(
            client_id=client_id,
            client_secret=client_secret,
            gateway_url=gateway_url,
            version=version,
            sign_method=sign_method,
        )
        cfg.validate()
        return cfg

    def validate(self) -> None:
        if not self.client_id:
            raise JdJosConfigError("jd client_id is required")
        if not self.client_secret:
            raise JdJosConfigError("jd client_secret is required")
        if not self.gateway_url:
            raise JdJosConfigError("jd gateway_url is required")
        if self.sign_method != "md5":
            raise JdJosConfigError(
                f"unsupported jd sign_method: {self.sign_method!r}"
            )
        if not self.version:
            raise JdJosConfigError("jd api version is required")


def build_jd_jos_config_from_model(row: JdAppConfig) -> JdJosConfig:
    if row is None:
        raise JdJosConfigError("jd app config row is required")

    return JdJosConfig.from_mapping(
        {
            "client_id": row.client_id,
            "client_secret": row.client_secret,
            "gateway_url": row.gateway_url,
            "sign_method": row.sign_method,
            "version": DEFAULT_JD_API_VERSION,
        }
    )


def build_jd_callback_url_from_model(row: JdAppConfig) -> str:
    if row is None:
        raise JdJosConfigError("jd app config row is required")

    value = str(row.callback_url or "").strip()
    if not value:
        raise JdJosConfigError("jd callback_url is required")
    return value


def load_jd_jos_config_from_env() -> JdJosConfig:
    return JdJosConfig.from_mapping(
        {
            "client_id": os.getenv("JD_CLIENT_ID"),
            "client_secret": os.getenv("JD_CLIENT_SECRET"),
            "gateway_url": os.getenv("JD_GATEWAY_URL", DEFAULT_JD_GATEWAY_URL),
            "version": os.getenv("JD_API_VERSION", DEFAULT_JD_API_VERSION),
            "sign_method": os.getenv("JD_SIGN_METHOD", DEFAULT_JD_SIGN_METHOD),
        }
    )


def try_load_jd_jos_config_from_env() -> Optional[JdJosConfig]:
    client_id = str(os.getenv("JD_CLIENT_ID") or "").strip()
    client_secret = str(os.getenv("JD_CLIENT_SECRET") or "").strip()

    if not client_id or not client_secret:
        return None

    return JdJosConfig.from_mapping(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "gateway_url": os.getenv("JD_GATEWAY_URL", DEFAULT_JD_GATEWAY_URL),
            "version": os.getenv("JD_API_VERSION", DEFAULT_JD_API_VERSION),
            "sign_method": os.getenv("JD_SIGN_METHOD", DEFAULT_JD_SIGN_METHOD),
        }
    )


def load_jd_callback_url_from_env() -> str:
    value = str(os.getenv("JD_CALLBACK_URL") or "").strip()
    if not value:
        raise JdJosConfigError("JD_CALLBACK_URL is required")
    return value
