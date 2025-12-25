# app/services/channel_inventory_v2.py
from __future__ import annotations

from typing import List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.channel_inventory_types import BatchQty, ChannelInventory


class ChannelInventoryV2:
    """
    v2 实际可售：单仓 / 多仓 / store-aware

    该类只负责“实时库存口径”：
      - on_hand / reserved_open / available / batches
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_single_item(
        self,
        platform: str,
        shop_id: str,
        warehouse_id: int,
        item_id: int,
    ) -> ChannelInventory:
        """
        单仓视图（给 API / UI 用）：

        - on_hand       = Σ stocks.qty
        - reserved_open = Σ (rl.qty - rl.consumed_qty)，仅 status='open'
        - available     = max(on_hand - reserved_open, 0)
        """
        on_hand = await self._get_on_hand(warehouse_id, item_id)
        reserved_open = await self._get_reserved_open(
            platform=platform,
            shop_id=shop_id,
            warehouse_id=warehouse_id,
            item_id=item_id,
        )
        batches = await self._get_batches(warehouse_id, item_id)

        available = on_hand - reserved_open
        if available < 0:
            available = 0

        return ChannelInventory(
            platform=platform,
            shop_id=shop_id,
            warehouse_id=warehouse_id,
            item_id=item_id,
            on_hand=on_hand,
            reserved_open=reserved_open,
            available=available,
            batches=batches,
        )

    async def get_multi_item(
        self,
        platform: str,
        shop_id: str,
        item_id: int,
    ) -> List[ChannelInventory]:
        """
        多仓视角查询：按 (platform, shop_id, item_id) 返回所有有“存在感”的仓。

        仓的来源（去重后的 union）：
          - stocks 中有该 item 的仓；
          - reservations(open) 中有该 item 的仓。
        """
        warehouse_ids = await self._get_relevant_warehouses(
            platform=platform,
            shop_id=shop_id,
            item_id=item_id,
        )
        if not warehouse_ids:
            return []

        results: List[ChannelInventory] = []
        for wid in warehouse_ids:
            ci = await self.get_single_item(
                platform=platform,
                shop_id=shop_id,
                warehouse_id=wid,
                item_id=item_id,
            )
            results.append(ci)
        return results

    async def get_multi_item_for_store(
        self,
        platform: str,
        shop_id: str,
        item_id: int,
    ) -> List[ChannelInventory]:
        """
        Store-aware 版本的多仓查询：

        1. 优先使用 store_warehouse：
           - 取该店铺绑定的所有仓（active=true），按 is_top DESC, priority ASC, warehouse_id 排序；
        2. 若未配置任何绑定，则回落到 get_multi_item 的旧逻辑。

        返回仍然是 ChannelInventory 列表，仓顺序与 store_warehouse 绑定顺序一致。
        """
        rows = await self.session.execute(
            text(
                """
                SELECT sw.warehouse_id
                  FROM store_warehouse AS sw
                  JOIN stores AS s
                    ON sw.store_id = s.id
                 WHERE s.platform = :platform
                   AND s.shop_id  = :shop_id
                   AND s.active   = TRUE
                 ORDER BY sw.is_top DESC,
                          sw.priority ASC,
                          sw.warehouse_id ASC
                """
            ),
            {"platform": platform.upper(), "shop_id": shop_id},
        )
        bound_ids = [int(r[0]) for r in rows.fetchall() if r[0] is not None]

        if bound_ids:
            warehouse_ids = bound_ids
        else:
            warehouse_ids = await self._get_relevant_warehouses(
                platform=platform,
                shop_id=shop_id,
                item_id=item_id,
            )

        if not warehouse_ids:
            return []

        results: List[ChannelInventory] = []
        for wid in warehouse_ids:
            ci = await self.get_single_item(
                platform=platform,
                shop_id=shop_id,
                warehouse_id=wid,
                item_id=item_id,
            )
            results.append(ci)
        return results

    async def _get_relevant_warehouses(
        self,
        platform: str,
        shop_id: str,
        item_id: int,
    ) -> List[int]:
        rows = await self.session.execute(
            text(
                """
                SELECT DISTINCT warehouse_id
                  FROM stocks
                 WHERE item_id = :i

                UNION

                SELECT DISTINCT r.warehouse_id
                  FROM reservations r
                  JOIN reservation_lines rl
                    ON rl.reservation_id = r.id
                 WHERE r.platform = :platform
                   AND r.shop_id  = :shop_id
                   AND rl.item_id = :i
                """
            ),
            {
                "platform": platform,
                "shop_id": shop_id,
                "i": item_id,
            },
        )
        ids = [int(r[0]) for r in rows.fetchall() if r[0] is not None]
        ids.sort()
        return ids

    async def _get_on_hand(self, warehouse_id: int, item_id: int) -> int:
        row = await self.session.execute(
            text(
                """
                SELECT COALESCE(SUM(qty), 0) AS on_hand
                FROM stocks
                WHERE warehouse_id = :w
                  AND item_id      = :i
                """
            ),
            {"w": warehouse_id, "i": item_id},
        )
        v = row.scalar()
        return int(v or 0)

    async def _get_reserved_open(
        self,
        platform: str,
        shop_id: str,
        warehouse_id: int,
        item_id: int,
    ) -> int:
        row = await self.session.execute(
            text(
                """
                SELECT
                    COALESCE(
                        SUM(rl.qty - rl.consumed_qty),
                        0
                    ) AS reserved_open
                FROM reservation_lines AS rl
                JOIN reservations AS r
                  ON r.id = rl.reservation_id
                WHERE r.platform     = :platform
                  AND r.shop_id      = :shop_id
                  AND r.warehouse_id = :w
                  AND r.status       = 'open'
                  AND rl.item_id     = :i
                """
            ),
            {
                "platform": platform,
                "shop_id": shop_id,
                "w": warehouse_id,
                "i": item_id,
            },
        )
        v = row.scalar()
        return int(v or 0)

    async def _get_batches(self, warehouse_id: int, item_id: int) -> List[BatchQty]:
        rows = (
            await self.session.execute(
                text(
                    """
                    SELECT batch_code, qty
                    FROM stocks
                    WHERE warehouse_id = :w
                      AND item_id      = :i
                      AND qty <> 0
                    ORDER BY batch_code
                    """
                ),
                {"w": warehouse_id, "i": item_id},
            )
        ).all()
        return [BatchQty(batch_code=r[0], qty=int(r[1] or 0)) for r in rows]
