# app/oms/platforms/taobao/settings.py
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping, Optional

from app.oms.platforms.models.taobao_app_config import TaobaoAppConfig

from .errors import TaobaoTopConfigError


DEFAULT_TOP_API_BASE_URL = "https://eco.taobao.com/router/rest"
DEFAULT_TOP_SIGN_METHOD = "md5"


@dataclass(frozen=True)
class TaobaoTopConfig:
    """
    OMS 淘宝 / TOP 协议配置。

    说明：
    - 当前已支持从数据库配置表构造
    - 环境变量读取函数暂时保留为过渡能力
    """

    app_key: str
    app_secret: str
    api_base_url: str = DEFAULT_TOP_API_BASE_URL
    sign_method: str = DEFAULT_TOP_SIGN_METHOD

    @classmethod
    def from_mapping(
        cls,
        data: Mapping[str, object],
    ) -> "TaobaoTopConfig":
        app_key = str(data.get("app_key") or "").strip()
        app_secret = str(data.get("app_secret") or "").strip()
        api_base_url = str(data.get("api_base_url") or DEFAULT_TOP_API_BASE_URL).strip()
        sign_method = str(data.get("sign_method") or DEFAULT_TOP_SIGN_METHOD).strip().lower()

        cfg = cls(
            app_key=app_key,
            app_secret=app_secret,
            api_base_url=api_base_url,
            sign_method=sign_method,
        )
        cfg.validate()
        return cfg

    def validate(self) -> None:
        if not self.app_key:
            raise TaobaoTopConfigError("taobao top app_key is required")
        if not self.app_secret:
            raise TaobaoTopConfigError("taobao top app_secret is required")
        if not self.api_base_url:
            raise TaobaoTopConfigError("taobao top api_base_url is required")
        if self.sign_method not in {"md5", "hmac"}:
            raise TaobaoTopConfigError(
                f"unsupported taobao top sign_method: {self.sign_method!r}"
            )


def build_taobao_top_config_from_model(row: TaobaoAppConfig) -> TaobaoTopConfig:
    if row is None:
        raise TaobaoTopConfigError("taobao app config row is required")

    return TaobaoTopConfig.from_mapping(
        {
            "app_key": row.app_key,
            "app_secret": row.app_secret,
            "api_base_url": row.api_base_url,
            "sign_method": row.sign_method,
        }
    )


def build_taobao_callback_url_from_model(row: TaobaoAppConfig) -> str:
    if row is None:
        raise TaobaoTopConfigError("taobao app config row is required")

    value = str(row.callback_url or "").strip()
    if not value:
        raise TaobaoTopConfigError("taobao callback_url is required")
    return value


def load_taobao_top_config_from_env() -> TaobaoTopConfig:
    """
    严格读取：
    - 缺少必要配置就直接抛错
    - 仅保留为过渡能力
    """
    return TaobaoTopConfig.from_mapping(
        {
            "app_key": os.getenv("TAOBAO_TOP_APP_KEY"),
            "app_secret": os.getenv("TAOBAO_TOP_APP_SECRET"),
            "api_base_url": os.getenv("TAOBAO_TOP_API_BASE_URL"),
            "sign_method": os.getenv("TAOBAO_TOP_SIGN_METHOD", DEFAULT_TOP_SIGN_METHOD),
        }
    )


def try_load_taobao_top_config_from_env() -> Optional[TaobaoTopConfig]:
    """
    宽松读取：
    - 仅当 app_key/app_secret 同时存在时才返回配置
    - 否则返回 None
    - 仅保留为过渡能力
    """
    app_key = str(os.getenv("TAOBAO_TOP_APP_KEY") or "").strip()
    app_secret = str(os.getenv("TAOBAO_TOP_APP_SECRET") or "").strip()

    if not app_key or not app_secret:
        return None

    return TaobaoTopConfig.from_mapping(
        {
            "app_key": app_key,
            "app_secret": app_secret,
            "api_base_url": os.getenv("TAOBAO_TOP_API_BASE_URL"),
            "sign_method": os.getenv("TAOBAO_TOP_SIGN_METHOD", DEFAULT_TOP_SIGN_METHOD),
        }
    )


def load_taobao_callback_url_from_env() -> str:
    """
    严格读取 callback_url。
    - 仅保留为过渡能力
    """
    value = str(os.getenv("TAOBAO_TOP_CALLBACK_URL") or "").strip()
    if not value:
        raise TaobaoTopConfigError("TAOBAO_TOP_CALLBACK_URL is required")
    return value
