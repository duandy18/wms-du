# app/services/oauth_unified_types.py
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Literal, Tuple

Platform = Literal["pdd", "tb", "jd"]


class PlatformOAuthError(Exception):
    pass


@dataclass
class PlatformOAuthConfig:
    platform: Platform
    authorize_url: str  # 浏览器跳转授权页的 base URL
    token_url: str  # 后端换取 access_token 的 URL
    client_id_env: str
    client_secret_env: str
    redirect_path: str  # 例如 "/oauth/pdd/callback"


PLATFORM_CONFIGS: Dict[Platform, PlatformOAuthConfig] = {
    "pdd": PlatformOAuthConfig(
        platform="pdd",
        authorize_url="https://fuwu.pinduoduo.com/service-market/auth",
        token_url="https://api.pinduoduo.com/router/router",  # POP 网关
        client_id_env="PDD_CLIENT_ID",
        client_secret_env="PDD_CLIENT_SECRET",
        redirect_path="/oauth/pdd/callback",
    ),
    "tb": PlatformOAuthConfig(
        platform="tb",
        authorize_url="https://oauth.taobao.com/authorize",
        token_url="https://oauth.taobao.com/token",
        client_id_env="TB_CLIENT_ID",
        client_secret_env="TB_CLIENT_SECRET",
        redirect_path="/oauth/tb/callback",
    ),
    "jd": PlatformOAuthConfig(
        platform="jd",
        authorize_url="https://open-oauth.jd.com/oauth2/to_login",
        token_url="https://open-oauth.jd.com/oauth2/access_token",
        client_id_env="JD_CLIENT_ID",
        client_secret_env="JD_CLIENT_SECRET",
        redirect_path="/oauth/jd/callback",
    ),
}


def load_credentials(cfg: PlatformOAuthConfig) -> Tuple[str, str]:
    client_id = os.getenv(cfg.client_id_env, "")
    client_secret = os.getenv(cfg.client_secret_env, "")
    if not (client_id and client_secret):
        raise PlatformOAuthError(
            f"{cfg.platform} 缺少环境变量 {cfg.client_id_env}/{cfg.client_secret_env}"
        )
    return client_id, client_secret
