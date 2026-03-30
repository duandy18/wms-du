# app/oms/platforms/pdd/settings.py
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping, Optional

from app.models.pdd_app_config import PddAppConfig


DEFAULT_PDD_API_BASE_URL = "https://gw-api.pinduoduo.com/api/router"
DEFAULT_PDD_SIGN_METHOD = "md5"


class PddOpenConfigError(ValueError):
    """OMS 拼多多开放平台配置异常。"""


@dataclass(frozen=True)
class PddOpenConfig:
    """
    OMS 拼多多开放平台协议配置。

    说明：
    - 当前支持从数据库配置表构造
    - 环境变量读取函数暂时保留为过渡能力
    """

    client_id: str
    client_secret: str
    api_base_url: str = DEFAULT_PDD_API_BASE_URL
    sign_method: str = DEFAULT_PDD_SIGN_METHOD

    @classmethod
    def from_mapping(
        cls,
        data: Mapping[str, object],
    ) -> "PddOpenConfig":
        client_id = str(data.get("client_id") or "").strip()
        client_secret = str(data.get("client_secret") or "").strip()
        api_base_url = str(data.get("api_base_url") or DEFAULT_PDD_API_BASE_URL).strip()
        sign_method = str(data.get("sign_method") or DEFAULT_PDD_SIGN_METHOD).strip().lower()

        cfg = cls(
            client_id=client_id,
            client_secret=client_secret,
            api_base_url=api_base_url,
            sign_method=sign_method,
        )
        cfg.validate()
        return cfg

    def validate(self) -> None:
        if not self.client_id:
            raise PddOpenConfigError("pdd client_id is required")
        if not self.client_secret:
            raise PddOpenConfigError("pdd client_secret is required")
        if not self.api_base_url:
            raise PddOpenConfigError("pdd api_base_url is required")
        if self.sign_method not in {"md5"}:
            raise PddOpenConfigError(
                f"unsupported pdd sign_method: {self.sign_method!r}"
            )


def build_pdd_open_config_from_model(row: PddAppConfig) -> PddOpenConfig:
    if row is None:
        raise PddOpenConfigError("pdd app config row is required")

    return PddOpenConfig.from_mapping(
        {
            "client_id": row.client_id,
            "client_secret": row.client_secret,
            "api_base_url": row.api_base_url,
            "sign_method": row.sign_method,
        }
    )


def build_pdd_redirect_uri_from_model(row: PddAppConfig) -> str:
    if row is None:
        raise PddOpenConfigError("pdd app config row is required")

    value = str(row.redirect_uri or "").strip()
    if not value:
        raise PddOpenConfigError("pdd redirect_uri is required")
    return value


def load_pdd_open_config_from_env() -> PddOpenConfig:
    """
    严格读取：
    - 缺少必要配置就直接抛错
    - 仅保留为过渡能力
    """
    return PddOpenConfig.from_mapping(
        {
            "client_id": os.getenv("PDD_OPEN_CLIENT_ID"),
            "client_secret": os.getenv("PDD_OPEN_CLIENT_SECRET"),
            "api_base_url": os.getenv("PDD_OPEN_API_BASE_URL"),
            "sign_method": os.getenv("PDD_OPEN_SIGN_METHOD", DEFAULT_PDD_SIGN_METHOD),
        }
    )


def try_load_pdd_open_config_from_env() -> Optional[PddOpenConfig]:
    """
    宽松读取：
    - 仅当 client_id/client_secret 同时存在时才返回配置
    - 否则返回 None
    - 仅保留为过渡能力
    """
    client_id = str(os.getenv("PDD_OPEN_CLIENT_ID") or "").strip()
    client_secret = str(os.getenv("PDD_OPEN_CLIENT_SECRET") or "").strip()

    if not client_id or not client_secret:
        return None

    return PddOpenConfig.from_mapping(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "api_base_url": os.getenv("PDD_OPEN_API_BASE_URL"),
            "sign_method": os.getenv("PDD_OPEN_SIGN_METHOD", DEFAULT_PDD_SIGN_METHOD),
        }
    )


def load_pdd_redirect_uri_from_env() -> str:
    """
    严格读取 redirect_uri。
    - 仅保留为过渡能力
    """
    value = str(os.getenv("PDD_OPEN_REDIRECT_URI") or "").strip()
    if not value:
        raise PddOpenConfigError("PDD_OPEN_REDIRECT_URI is required")
    return value
