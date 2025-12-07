# app/adapters/base.py
from __future__ import annotations

from typing import Any, Dict, Protocol, Sequence


class ChannelAdapter(Protocol):
    """
    平台适配接口（最小骨架）
    - 仅定义我们现阶段需要的“库存拉取/推送/签名”形状
    """

    async def fetch_inventory(self, *, store_id: int, item_ids: Sequence[int]) -> Dict[int, int]:
        """
        拉取平台侧库存（店内的若干 item）。
        返回: {item_id: platform_qty}
        """
        ...

    async def push_inventory(self, *, store_id: int, items: Sequence[dict]) -> Dict[str, Any]:
        """
        推送可见量到平台。
        items: [{"item_id": 777, "qty": 10}, ...]
        返回: 平台响应（或统一包装）
        """
        ...

    def sign(self, payload: dict) -> str:
        """
        平台签名（如需）。
        """
        ...
