# app/adapters/pdd.py
from __future__ import annotations
from typing import Sequence, Dict, Any

from app.adapters.base import ChannelAdapter


class PddAdapter(ChannelAdapter):
    """
    拼多多适配器（占位实现）
    - 现阶段仅给出形状；真实对接时在这里调用 PDD SDK / API
    """

    async def fetch_inventory(self, *, store_id: int, item_ids: Sequence[int]) -> Dict[int, int]:
        # TODO: 调 PDD 接口，按 store_id + ext_sku_id 映射获取平台库存
        # 现在作为占位：返回全 0，便于影子期对账
        return {int(i): 0 for i in item_ids}

    async def push_inventory(self, *, store_id: int, items: Sequence[dict]) -> Dict[str, Any]:
        # TODO: 调 PDD 批量推库存接口（限流、签名、重试）
        return {"ok": False, "reason": "PDD push not wired yet", "preview": list(items)}

    def sign(self, payload: dict) -> str:
        # TODO: PDD 的签名算法（按 app_key/secret）
        return "pdd-signature-placeholder"
