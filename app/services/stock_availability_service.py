# app/services/stock_availability_service.py
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class StockAvailabilityService:
    """
    ✅ 真实库存可售（事实层）唯一入口：单仓可售 raw 值

    口径（Phase 4.x）：
        available_raw = Σ stocks.qty
                        - Σ open reservations 的未消费数量（rl.qty - rl.consumed_qty）

    特性：
    - 返回值允许为负数（用于 anti-oversell 检查与 UT 验证）
    - 展示层 / UI 若要“可理解值”，再自行 max(available_raw, 0)

    注意：
    - platform/shop_id 作为入参保留（保持调用合同稳定），但当前 SQL 不过滤它们
      （你现在就是“全局 open reservations”口径）
    """

    @staticmethod
    async def get_available_for_item(
        session: AsyncSession,
        *,
        platform: str,
        shop_id: str,
        warehouse_id: int,
        item_id: int,
    ) -> int:
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
            "warehouse_id": int(warehouse_id),
            "item_id": int(item_id),
        }

        result = await session.execute(sql, params)
        available = result.scalar_one_or_none()
        return int(available or 0)

    @staticmethod
    async def get_available_for_items(
        session: AsyncSession,
        *,
        platform: str,
        shop_id: str,
        warehouse_id: int,
        item_ids: list[int],
    ) -> dict[int, int]:
        """
        批量版可售查询（Explain / 扫描等只读场景使用）：

        输入：
        - warehouse_id
        - item_ids[]

        输出：
        - { item_id: available_raw }

        语义说明：
        - available_raw 允许为负数（与单 item 版本一致）
        - platform / shop_id 作为形参保留，保持调用合同稳定
        """
        ids = [int(x) for x in (item_ids or []) if int(x) > 0]
        if not ids:
            return {}

        sql = text(
            """
            WITH stocks_agg AS (
                SELECT s.item_id, COALESCE(SUM(s.qty), 0) AS qty
                FROM stocks AS s
                WHERE s.warehouse_id = :warehouse_id
                  AND s.item_id = ANY(:item_ids)
                GROUP BY s.item_id
            ),
            reserve_agg AS (
                SELECT rl.item_id, COALESCE(SUM(rl.qty - COALESCE(rl.consumed_qty, 0)), 0) AS qty
                FROM reservations AS r
                JOIN reservation_lines AS rl
                  ON rl.reservation_id = r.id
                WHERE r.warehouse_id = :warehouse_id
                  AND r.status       = 'open'
                  AND rl.item_id     = ANY(:item_ids)
                GROUP BY rl.item_id
            )
            SELECT
              i.item_id AS item_id,
              COALESCE(sa.qty, 0) - COALESCE(ra.qty, 0) AS available
            FROM (
              SELECT UNNEST(:item_ids) AS item_id
            ) AS i
            LEFT JOIN stocks_agg  AS sa ON sa.item_id = i.item_id
            LEFT JOIN reserve_agg AS ra ON ra.item_id = i.item_id
            ORDER BY i.item_id
            """
        )

        params = {
            "platform": platform,   # 保持参数形态稳定（不使用）
            "shop_id": shop_id,     # 保持参数形态稳定（不使用）
            "warehouse_id": int(warehouse_id),
            "item_ids": ids,
        }

        rows = (await session.execute(sql, params)).mappings().all()
        out: dict[int, int] = {}
        for r in rows:
            out[int(r["item_id"])] = int(r.get("available") or 0)
        return out


__all__ = ["StockAvailabilityService"]
