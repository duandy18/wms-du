# app/adapters/pdd.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.base import ChannelAdapter
from app.services.store_token_service import (
    StoreTokenExpired,
    StoreTokenNotFound,
    StoreTokenService,
)


@dataclass
class PddCredentials:
    """
    应用级凭据（AppKey / AppSecret / 回调地址）。

    说明：
    - 当前仅作为结构占位；
    - 后续可从独立配置表 / 环境变量中加载；
    - 不再与任何 SKU / PSKU / mirror 语义耦合。
    """

    app_key: Optional[str] = None
    app_secret: Optional[str] = None
    callback_url: Optional[str] = None

    @property
    def ready(self) -> bool:
        return bool(self.app_key and self.app_secret)


class PddAdapter(ChannelAdapter):
    """
    拼多多适配器（精简版）

    当前职责（明确、克制）：
    - 加载店铺级 token（用于后续真实 API 对接）
    - 提供库存 fetch / push 的占位接口
    - 提供 sign 占位

    明确不再承担的职责（已下线）：
    - platform SKU / PSKU
    - SKU mirror / raw_payload
    - fetch preview / ext_sku_ids
    """

    async def load_credentials(self, session: AsyncSession, *, store_id: int) -> PddCredentials:
        _ = session
        _ = store_id
        return PddCredentials()

    async def load_token(self, session: AsyncSession, *, store_id: int) -> Optional[str]:
        svc = StoreTokenService(session)
        try:
            rec = await svc.get_token_for_store(store_id=store_id, platform="pdd")
        except (StoreTokenNotFound, StoreTokenExpired):
            return None
        return rec.access_token

    async def fetch_inventory(self, *, store_id: int, item_ids: Sequence[int]) -> Dict[int, int]:
        """
        拉取库存（占位）

        说明：
        - 当前不对接真实 PDD API；
        - 只返回 item_id → 0 的形态，作为接口占位；
        - 不涉及任何 SKU / PSKU / mirror 语义。
        """
        _ = store_id
        return {int(i): 0 for i in item_ids}

    async def push_inventory(self, *, store_id: int, items: Sequence[dict]) -> Dict[str, Any]:
        """
        推送库存（占位）
        """
        _ = store_id
        _ = items
        return {"ok": False, "reason": "PDD push not wired yet"}

    def sign(self, payload: dict) -> str:
        _ = payload
        return "pdd-signature-placeholder"
