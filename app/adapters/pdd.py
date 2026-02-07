# app/adapters/pdd.py
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence

from sqlalchemy import text
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

    注意：
    - 目前仅作为占位结构存在；
    - 真实的 app_key / app_secret 以后可以从单独的配置表 / 环境变量获取，
      不再耦合在 Store 模型里。
    """

    app_key: Optional[str] = None
    app_secret: Optional[str] = None
    callback_url: Optional[str] = None

    @property
    def ready(self) -> bool:
        return bool(self.app_key and self.app_secret)


class PddAdapter(ChannelAdapter):
    """
    拼多多适配器（骨架版）

    当前职责：
    - 预览拉库存请求参数（platform_sku_ids → ext_sku_ids）；
    - 预埋店铺级 token 的加载方法（load_token），为后续接真实 API 做准备；
    - fetch/push 仍为占位。

    ✅ 强制收敛：
    - build_fetch_preview **只允许** platform_sku_ids（PSKU 入口）；
    - ext_sku_ids **只来源于** platform_sku_mirror.raw_payload；
    - 禁止 item_ids（避免把库存域/商品域入口重新塞回平台域）。
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

    @staticmethod
    def _extract_ext_sku_id_from_raw(raw_payload: Any, *, fallback: str) -> str:
        if raw_payload is None:
            return fallback

        obj: Any = raw_payload
        if isinstance(raw_payload, str):
            try:
                obj = json.loads(raw_payload)
            except Exception:
                return fallback

        if not isinstance(obj, dict):
            return fallback

        candidates = [
            "pdd_sku_id",
            "pddSkuId",
            "sku_id",
            "skuId",
            "outer_id",
            "outerId",
            "spec_id",
            "specId",
            "id",
        ]
        for k in candidates:
            v = obj.get(k)
            if v is None:
                continue
            if isinstance(v, (int, float)):
                return str(int(v))
            if isinstance(v, str) and v.strip():
                return v.strip()

        return fallback

    async def build_fetch_preview(
        self,
        session: AsyncSession,
        *,
        store_id: int,
        platform_sku_ids: Sequence[str],
        platform: str = "PDD",
    ) -> Dict[str, Any]:
        """
        返回“将要请求 PDD 拉库存”的预览（不真正调用平台）。

        输入：
        - platform_sku_ids：平台 SKU 标识（PSKU 的 platform_sku_id）
        - store_id：内部店铺 ID（当前约定 shop_id == store_id）
        - platform：默认 PDD

        输出：
        - ext_sku_ids：平台接口需要的 SKU 标识（来自 mirror.raw_payload；找不到则回落为 platform_sku_id）
        """
        creds = await self.load_credentials(session, store_id=store_id)
        token = await self.load_token(session, store_id=store_id)

        ids = [str(x) for x in platform_sku_ids]
        ext_by_id: dict[str, str] = {pid: pid for pid in ids}

        if ids:
            sql = text(
                """
                SELECT platform_sku_id, raw_payload
                  FROM platform_sku_mirror
                 WHERE platform = :platform
                   AND shop_id = :shop_id
                   AND platform_sku_id = ANY(:ids)
                """
            )
            rows = (
                await session.execute(
                    sql,
                    {"platform": str(platform), "shop_id": int(store_id), "ids": list(ids)},
                )
            ).mappings().all()

            for r in rows:
                pid = str(r.get("platform_sku_id") or "")
                if not pid:
                    continue
                raw = r.get("raw_payload")
                ext_by_id[pid] = self._extract_ext_sku_id_from_raw(raw, fallback=pid)

        ext = [ext_by_id.get(pid, pid) for pid in ids]

        payload = {"store_id": store_id, "platform": str(platform), "platform_sku_ids": ids, "ext_sku_ids": ext}
        sig = self.sign(payload)

        return {
            "creds_ready": creds.ready,
            "has_token": bool(token),
            "store_id": store_id,
            "platform": str(platform),
            "platform_sku_ids": ids,
            "ext_sku_ids": ext,
            "signature": sig,
        }

    async def fetch_inventory(self, *, store_id: int, item_ids: Sequence[int]) -> Dict[int, int]:
        _ = store_id
        return {int(i): 0 for i in item_ids}

    async def push_inventory(self, *, store_id: int, items: Sequence[dict]) -> Dict[str, Any]:
        _ = store_id
        return {"ok": False, "reason": "PDD push not wired yet", "preview": list(items)}

    def sign(self, payload: dict) -> str:
        _ = payload
        return "pdd-signature-placeholder"
