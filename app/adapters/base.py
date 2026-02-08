# app/adapters/base.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional, Protocol, Sequence


@dataclass(frozen=True)
class PlatformSkuMirrorItem:
    platform_sku_id: str
    sku_name: Optional[str] = None
    spec: Optional[str] = None
    raw_payload: Optional[dict[str, Any]] = None
    observed_at: Optional[datetime] = None
    source: str = "platform-sync"


class ChannelAdapter(Protocol):
    """
    平台适配接口（最小骨架）
    - 仅定义我们现阶段需要的“库存拉取/推送/签名/镜像拉取”形状
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

    async def fetch_sku_mirrors(
        self,
        *,
        store_id: int,
        platform_sku_ids: Sequence[str],
    ) -> Sequence[PlatformSkuMirrorItem]:
        """
        拉取平台 SKU 镜像（用于写入 platform_sku_mirror）
        - platform_sku_ids：平台 SKU 标识（PSKU 锚点）
        - 返回：镜像条目（可只给 raw_payload；sku_name/spec 可由 mirror service 从 payload 提取）
        """
        ...

    def sign(self, payload: dict) -> str:
        """
        平台签名（如需）。
        """
        ...
