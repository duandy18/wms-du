# app/services/pdd_auth_service.py
from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Tuple

import httpx
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.store_token import StoreToken

# ===== 配置：先用环境变量，后面你可以接到自己的 settings 体系 =====
PDD_CLIENT_ID = os.getenv("PDD_CLIENT_ID", "")
PDD_CLIENT_SECRET = os.getenv("PDD_CLIENT_SECRET", "")
PDD_REDIRECT_URI = os.getenv("PDD_REDIRECT_URI", "")  # 必须和开放平台配置一致

# 拼多多商家授权页（Web）
PDD_AUTHORIZE_URL = "https://fuwu.pinduoduo.com/service-market/auth"
# 拼多多统一网关（大部分 API 都走这个，type 区分具体接口）
PDD_API_GATEWAY = "https://api.pinduoduo.com/router/router"


class PddAuthError(Exception):
    pass


class PddAuthService:
    """
    PDD OAuth 授权服务：生成授权 URL & 用 code 换 token & 落库。
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ---------- 第一步：生成授权 URL ----------

    async def build_auth_url(self, store_id: int) -> str:
        """
        为某个内部 store 生成 PDD 授权 URL。

        state 里简单塞入 store_id，形式：<random>.<store_id>
        内网系统，用这个就够了；以后想更严谨，可以把 state 存 Redis。
        """
        if not (PDD_CLIENT_ID and PDD_REDIRECT_URI):
            raise PddAuthError("PDD_CLIENT_ID / PDD_REDIRECT_URI 未配置")

        rand = secrets.token_urlsafe(16)
        state = f"{rand}.{store_id}"

        from urllib.parse import urlencode

        params = {
            "response_type": "code",
            "client_id": PDD_CLIENT_ID,
            "redirect_uri": PDD_REDIRECT_URI,
            "state": state,
        }
        return f"{PDD_AUTHORIZE_URL}?{urlencode(params)}"

    # ---------- 第二步：处理回调，用 code 换 token ----------

    async def handle_callback(self, code: str, state: str) -> Tuple[StoreToken, int]:
        """
        用拼多多回调给的 code 换 access_token / refresh_token，并更新 store_tokens。

        返回：(StoreToken 对象, store_id)
        """
        store_id = self._parse_store_id_from_state(state)

        token_data = await self._exchange_code_for_token(code)

        # 下面字段名以文档为准，不同 SDK 返回结构有差异：
        # 常见格式：{"access_token": "...", "refresh_token": "...", "expires_in": 86400, "owner_id": "xxx", ...}
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in")
        mall_id = str(token_data.get("owner_id") or "")

        if not (access_token and refresh_token and expires_in):
            raise PddAuthError(f"拼多多返回数据不完整: {token_data!r}")

        expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))

        # upsert store_tokens（同一个 store + platform=pdd 只有一条记录）
        stmt = sa.select(StoreToken).where(
            StoreToken.store_id == store_id,
            StoreToken.platform == "pdd",
        )
        result = await self.db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            existing.access_token = access_token
            existing.refresh_token = refresh_token
            existing.expires_at = expires_at
            existing.mall_id = mall_id or existing.mall_id
            token_row = existing
        else:
            token_row = StoreToken(
                store_id=store_id,
                platform="pdd",
                mall_id=mall_id or None,
                access_token=access_token,
                refresh_token=refresh_token,
                expires_at=expires_at,
            )
            self.db.add(token_row)

        # TODO：这里可以顺便用 access_token 调一次 pdd.mall.info.get，把店铺名称同步到 stores 表
        # 留给我们下一步，等你贴 stores 模型和 schema 再补丁。

        await self.db.commit()
        await self.db.refresh(token_row)

        return token_row, store_id

    # ---------- 内部辅助 ----------

    def _parse_store_id_from_state(self, state: str) -> int:
        try:
            _, store_id_str = state.rsplit(".", 1)
            return int(store_id_str)
        except Exception as exc:
            raise PddAuthError(f"state 解析失败: {state!r}") from exc

    async def _exchange_code_for_token(self, code: str) -> dict:
        """
        调 PDD 网关，用授权码 code 换 access_token。

        对应文档：type = pdd.pop.auth.token.create
        """
        if not (PDD_CLIENT_ID and PDD_CLIENT_SECRET):
            raise PddAuthError("PDD_CLIENT_ID / PDD_CLIENT_SECRET 未配置")

        payload = {
            "type": "pdd.pop.auth.token.create",
            "client_id": PDD_CLIENT_ID,
            "client_secret": PDD_CLIENT_SECRET,
            "code": code,
            "data_type": "JSON",
            "timestamp": int(datetime.now().timestamp()),
        }

        # 实际上还需要签名 sign，这里先给你骨架，你接文档把签名逻辑加进去
        # payload["sign"] = calc_sign(payload, client_secret)

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(PDD_API_GATEWAY, data=payload)
            resp.raise_for_status()
            data = resp.json()

        # 不同 SDK 可能包装一层，这里先尝试两种方式
        if "error_response" in data:
            raise PddAuthError(f"PDD 授权失败: {data['error_response']}")

        # 许多实现会返回 { "pop_auth_token_create_response": { ... } }
        token_data = data.get("pop_auth_token_create_response") or data
        return token_data
