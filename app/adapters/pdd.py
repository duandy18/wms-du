# app/adapters/pdd.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.base import ChannelAdapter
from app.models.store import Store, StoreItem


@dataclass
class PddCredentials:
    app_key: Optional[str] = None
    app_secret: Optional[str] = None
    callback_url: Optional[str] = None

    @property
    def ready(self) -> bool:
        return bool(self.app_key and self.app_secret)


class PddAdapter(ChannelAdapter):
    """
    拼多多适配器（骨架）
    - 从 stores 读取凭据（app_key/app_secret/callback_url）
    - 构造“拉库存请求预览”（按 item_ids → ext_sku_ids 映射，顺序一致、无重复）
    - fetch/push 仍为占位，实现后续可无缝替换为 SDK/API
    """

    # ---------- 凭据 ----------
    async def load_credentials(self, session: AsyncSession, *, store_id: int) -> PddCredentials:
        row = await session.execute(
            select(Store.app_key, Store.app_secret, Store.callback_url).where(Store.id == store_id)
        )
        app_key, app_secret, callback_url = (row.first() or (None, None, None))
        return PddCredentials(
            app_key=app_key or None,
            app_secret=app_secret or None,
            callback_url=callback_url or None,
        )

    # ---------- 预览：构造拉库存入参（含 ext_sku 映射与签名占位） ----------
    async def build_fetch_preview(
        self, session: AsyncSession, *, store_id: int, item_ids: Sequence[int]
    ) -> Dict[str, Any]:
        """
        返回“将要请求 PDD 拉库存”的预览：
        {
          "creds_ready": true/false,
          "store_id": 1,
          "ext_sku_ids": ["...","..."],  # 与 item_ids 同顺序、无重复
          "signature": "pdd-signature-placeholder",
        }
        """
        creds = await self.load_credentials(session, store_id=store_id)

        # 一次性取出并缓存：避免重复 .all() 导致结果耗尽 / 误判未绑定
        result = await session.execute(
            select(StoreItem.item_id, StoreItem.pdd_sku_id)
            .where(StoreItem.store_id == store_id, StoreItem.item_id.in_(list(map(int, item_ids))))
        )
        rows = result.all()
        mapping = {int(i): (sku or str(int(i))) for i, sku in rows}

        # 按 item_ids 顺序映射；未绑定回落为 item_id 字符串
        ext = [mapping.get(int(iid), str(int(iid))) for iid in item_ids]

        payload = {"store_id": store_id, "ext_sku_ids": ext}
        sig = self.sign(payload)
        return {
            "creds_ready": creds.ready,
            "store_id": store_id,
            "ext_sku_ids": ext,
            "signature": sig,
        }

    # ---------- 拉库存（占位实现；后续接 SDK） ----------
    async def fetch_inventory(self, *, store_id: int, item_ids: Sequence[int]) -> Dict[int, int]:
        # TODO: 调 PDD 接口：把 item_ids 映射为 ext_sku_ids，带上签名/限流等
        return {int(i): 0 for i in item_ids}

    # ---------- 推库存（占位实现；后续接 SDK） ----------
    async def push_inventory(self, *, store_id: int, items: Sequence[dict]) -> Dict[str, Any]:
        # TODO: 调 PDD 批量推库存接口
        return {"ok": False, "reason": "PDD push not wired yet", "preview": list(items)}

    # ---------- 签名占位 ----------
    def sign(self, payload: dict) -> str:
        # TODO: 真实实现（通常由 app_secret 参与 HMAC/MD5）
        return "pdd-signature-placeholder"
