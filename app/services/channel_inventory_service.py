# app/services/channel_inventory_service.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.channel_inventory_legacy import adjust_reserved as _adjust_reserved
from app.services.channel_inventory_legacy import ensure_row as _ensure_row
from app.services.channel_inventory_legacy import set_visible as _set_visible
from app.services.channel_inventory_types import BatchQty, ChannelInventory
from app.services.channel_inventory_v2 import ChannelInventoryV2


class ChannelInventoryService:
    """
    ChannelInventory 唯一真相（统一服务）：

    1. 店铺侧 reserved_qty / visible（channel_inventory 表）：
       - adjust_reserved()
       - set_visible()
       这块是 legacy 的渠道可见层，仍然保留以兼容现有表结构。

    2. 实际可售库存 v2（单仓 / 多仓视图）：
       - get_single_item() 按单仓 (platform, shop, warehouse, item)
       - get_multi_item()  按“有存在感的仓”（stocks ∪ reservations）
       - get_multi_item_for_store() 按 store_warehouse 绑定的仓（store-aware）

    3. 可售内核入口：
       - get_available_for_item(session, platform, shop_id, warehouse_id, item_id)
         → 方案 2（全局剩余可售）口径：
             available_raw = Σ stocks.qty
                             - Σ (全局 open reservations 的未消费数量)
         返回值允许为负数（用于 anti-oversell 检查与测试验证）。
    """

    def __init__(self, session: Optional[AsyncSession] = None) -> None:
        self.session = session

    # ------------------------------------------------------------------ #
    # 1) 店铺侧 reserved_qty / visible（保留原逻辑）
    # ------------------------------------------------------------------ #

    @staticmethod
    async def _ensure_row(session: AsyncSession, *, store_id: int, item_id: int) -> None:
        """确保 channel_inventory(store_id,item_id) 存在（不提交）。"""
        await _ensure_row(session, store_id=store_id, item_id=item_id)

    @staticmethod
    async def adjust_reserved(
        session: AsyncSession,
        *,
        store_id: int,
        item_id: int,
        delta: int,
        ref: Optional[str] = None,
    ) -> Dict[str, Any]:
        return await _adjust_reserved(
            session,
            store_id=store_id,
            item_id=item_id,
            delta=delta,
            ref=ref,
        )

    @staticmethod
    async def set_visible(
        session: AsyncSession,
        *,
        store_id: int,
        item_id: int,
        visible: int,
    ) -> None:
        await _set_visible(
            session,
            store_id=store_id,
            item_id=item_id,
            visible=visible,
        )

    # ------------------------------------------------------------------ #
    # 2) v2 实际可售：单仓 / 多仓 / store-aware
    # ------------------------------------------------------------------ #

    async def get_single_item(
        self,
        platform: str,
        shop_id: str,
        warehouse_id: int,
        item_id: int,
    ) -> ChannelInventory:
        if self.session is None:
            raise RuntimeError("ChannelInventoryService(session=...) required for v2 methods")
        v2 = ChannelInventoryV2(self.session)
        return await v2.get_single_item(
            platform=platform,
            shop_id=shop_id,
            warehouse_id=warehouse_id,
            item_id=item_id,
        )

    async def get_multi_item(
        self,
        platform: str,
        shop_id: str,
        item_id: int,
    ) -> List[ChannelInventory]:
        if self.session is None:
            raise RuntimeError("ChannelInventoryService(session=...) required for v2 methods")
        v2 = ChannelInventoryV2(self.session)
        return await v2.get_multi_item(platform=platform, shop_id=shop_id, item_id=item_id)

    async def get_multi_item_for_store(
        self,
        platform: str,
        shop_id: str,
        item_id: int,
    ) -> List[ChannelInventory]:
        if self.session is None:
            raise RuntimeError("ChannelInventoryService(session=...) required for v2 methods")
        v2 = ChannelInventoryV2(self.session)
        return await v2.get_multi_item_for_store(
            platform=platform, shop_id=shop_id, item_id=item_id
        )

    async def get_multi_items_for_store(
        self,
        platform: str,
        shop_id: str,
        item_ids: List[int],
    ) -> Dict[int, List[ChannelInventory]]:
        """
        批量：按店铺维度批量获取多 item 的“多仓可售”（store-aware）。

        注意：方案 2 下 available/reserved_open 已是全局口径；
        这里的 store-aware 仅影响“候选仓集合与顺序”。
        """
        if self.session is None:
            raise RuntimeError("ChannelInventoryService(session=...) required for v2 methods")

        v2 = ChannelInventoryV2(self.session)
        out: Dict[int, List[ChannelInventory]] = {}

        for item_id in item_ids:
            out[item_id] = await v2.get_multi_item_for_store(
                platform=platform, shop_id=shop_id, item_id=item_id
            )

        return out

    # ---- 对外统一入口：给 reserve / 校验用的“单仓可售（raw 值）” ----

    async def get_available_for_item(
        self,
        session: AsyncSession,
        *,
        platform: str,
        shop_id: str,
        warehouse_id: int,
        item_id: int,
    ) -> int:
        """
        对外可售入口（唯一口径，单仓）——方案 2（全局剩余可售）：

            available_raw = Σ stocks.qty
                            - Σ (全局 open reservations 的未消费数量)

        特性：
        - 返回值允许为负数，用于：
            * anti-oversell 检查
            * test_channel_inventory_available 等测试验证
        - 展示层（API / UI）需要时再自行 max(available_raw, 0)。

        注意：platform/shop_id 仍保留为入参（保持调用点稳定），但不参与 SQL 过滤。
        """
        sql = text(
            """
            WITH stocks_agg AS (
                SELECT COALESCE(SUM(s.qty), 0) AS qty
                FROM stocks AS s
                WHERE s.item_id = :item_id
                  AND s.warehouse_id = :warehouse_id
            ),
            reserve_agg AS (
                SELECT COALESCE(SUM(rl.qty - COALESCE(rl.consumed_qty, 0)), 0) AS qty
                FROM reservations AS r
                JOIN reservation_lines AS rl
                  ON rl.reservation_id = r.id
                WHERE r.warehouse_id = :warehouse_id
                  AND r.status       = 'open'
                  AND rl.item_id     = :item_id
            )
            SELECT
                (SELECT qty FROM stocks_agg)
                -
                (SELECT qty FROM reserve_agg)
            AS available
            """
        )

        params = {
            "platform": platform,   # 保持参数形态稳定（不使用）
            "shop_id": shop_id,     # 保持参数形态稳定（不使用）
            "warehouse_id": warehouse_id,
            "item_id": item_id,
        }

        result = await session.execute(sql, params)
        available = result.scalar_one_or_none()
        return int(available or 0)


__all__ = [
    "BatchQty",
    "ChannelInventory",
    "ChannelInventoryService",
]
