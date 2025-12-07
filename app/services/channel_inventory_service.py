from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class BatchQty:
    batch_code: str
    qty: int


@dataclass
class ChannelInventory:
    platform: str
    shop_id: str
    warehouse_id: int
    item_id: int

    on_hand: int
    reserved_open: int
    available: int

    batches: List[BatchQty]


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
         → 使用 v1 CTE 公式：
             available_raw = Σ stocks.qty
                             - Σ (open reservations 的未消费数量)
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
        await session.execute(
            text(
                """
                INSERT INTO channel_inventory(store_id, item_id, reserved_qty)
                VALUES (:sid, :iid, 0)
                ON CONFLICT (store_id, item_id) DO NOTHING
                """
            ),
            {"sid": int(store_id), "iid": int(item_id)},
        )

    @staticmethod
    async def adjust_reserved(
        session: AsyncSession,
        *,
        store_id: int,
        item_id: int,
        delta: int,
        ref: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        调整店铺层 reserved_qty（支持 ref 幂等）：
        - delta > 0 占用，delta < 0 释放；
        - 若提供 ref：同一 ref 重复调用将被忽略；
        - 返回 {"reserved_total": int, "idempotent": bool}
        """
        idempotent_hit = False

        tx_ctx = session.begin_nested() if session.in_transaction() else session.begin()
        async with tx_ctx:
            # 0) 幂等钥匙表（无迁移依赖，首次调用自动建表）
            if ref:
                await session.execute(
                    text(
                        """
                        CREATE TABLE IF NOT EXISTS channel_reserved_idem(
                            ref        TEXT PRIMARY KEY,
                            store_id   BIGINT,
                            item_id    BIGINT,
                            delta      INTEGER,
                            created_at TIMESTAMP DEFAULT NOW()
                        )
                        """
                    )
                )
                ins = await session.execute(
                    text(
                        """
                        INSERT INTO channel_reserved_idem(ref, store_id, item_id, delta)
                        VALUES (:ref, :sid, :iid, :d)
                        ON CONFLICT (ref) DO NOTHING
                        """
                    ),
                    {"ref": ref, "sid": int(store_id), "iid": int(item_id), "d": int(delta)},
                )
                if ins.rowcount == 0:
                    idempotent_hit = True

            # 1) 确保目标行存在
            await ChannelInventoryService._ensure_row(session, store_id=store_id, item_id=item_id)

            # 2) 非幂等命中时执行调整（防负数）
            if not idempotent_hit and delta != 0:
                await session.execute(
                    text(
                        """
                        UPDATE channel_inventory
                        SET reserved_qty = GREATEST(reserved_qty + :d, 0)
                        WHERE store_id=:sid AND item_id=:iid
                        """
                    ),
                    {"sid": int(store_id), "iid": int(item_id), "d": int(delta)},
                )

            # 3) 读取最新 reserved_total
            total = (
                await session.execute(
                    text(
                        """
                            SELECT reserved_qty
                            FROM channel_inventory
                            WHERE store_id=:sid AND item_id=:iid
                            """
                    ),
                    {"sid": int(store_id), "iid": int(item_id)},
                )
            ).scalar_one_or_none() or 0

        await session.commit()
        return {"reserved_total": int(total), "idempotent": bool(idempotent_hit)}

    @staticmethod
    async def set_visible(
        session: AsyncSession,
        *,
        store_id: int,
        item_id: int,
        visible: int,
    ) -> None:
        """
        可见量写入（保留接口，不参与关键链路）。
        同时兼容两种列名：visible 优先；若存在 legacy 列 visible_qty，也一并更新。
        """
        v = int(max(visible, 0))

        tx_ctx = session.begin_nested() if session.in_transaction() else session.begin()
        async with tx_ctx:
            await ChannelInventoryService._ensure_row(session, store_id=store_id, item_id=item_id)

            # 写入 visible（若列存在）
            await session.execute(
                text(
                    """
                    DO $$
                    BEGIN
                      IF EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_schema='public'
                          AND table_name='channel_inventory'
                          AND column_name='visible'
                      ) THEN
                        UPDATE channel_inventory
                        SET visible=:v
                        WHERE store_id=:sid AND item_id=:iid;
                      END IF;
                    END $$;
                    """
                ),
                {"sid": int(store_id), "iid": int(item_id), "v": v},
            )

            # 兼容写入 legacy 列 visible_qty（若存在）
            await session.execute(
                text(
                    """
                    DO $$
                    BEGIN
                      IF EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_schema='public'
                          AND table_name='channel_inventory'
                          AND column_name='visible_qty'
                      ) THEN
                        UPDATE channel_inventory
                        SET visible_qty=:v
                        WHERE store_id=:sid AND item_id=:iid;
                      END IF;
                    END $$;
                    """
                ),
                {"sid": int(store_id), "iid": int(item_id), "v": v},
            )

        await session.commit()

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
        """
        单仓视图（给 API / UI 用）：

        - on_hand       = Σ stocks.qty
        - reserved_open = Σ (rl.qty - rl.consumed_qty)，仅 status='open'
        - available     = max(on_hand - reserved_open, 0)
        """
        if self.session is None:
            raise RuntimeError("ChannelInventoryService(session=...) required for v2 methods")

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
        if self.session is None:
            raise RuntimeError("ChannelInventoryService(session=...) required for v2 methods")

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
        if self.session is None:
            raise RuntimeError("ChannelInventoryService(session=...) required for v2 methods")

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

    # ---- 对外统一入口：给路由 / reserve / 测试用的“单仓可售（raw 值）” ----

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
        对外可售入口（唯一口径，单仓）：

            available_raw = Σ stocks.qty
                            - Σ (open reservations 的未消费数量)

        特性：
        - 返回值允许为负数，用于：
            * anti-oversell 检查
            * test_channel_inventory_available 等测试验证
        - 展示层（API / UI）需要时再自行 max(available_raw, 0)。
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
                WHERE r.platform     = :platform
                  AND r.shop_id      = :shop_id
                  AND r.warehouse_id = :warehouse_id
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
            "platform": platform,
            "shop_id": shop_id,
            "warehouse_id": warehouse_id,
            "item_id": item_id,
        }

        result = await session.execute(sql, params)
        available = result.scalar_one_or_none()
        return int(available or 0)

    # ------------------------------------------------------------------
    # 内部明细查询（v2 实现细节）
    # ------------------------------------------------------------------

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

    async def _get_batches(
        self,
        warehouse_id: int,
        item_id: int,
    ) -> List[BatchQty]:
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
