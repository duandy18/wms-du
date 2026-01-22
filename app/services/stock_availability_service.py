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
            "platform": platform,  # 保持参数形态稳定（不使用）
            "shop_id": shop_id,  # 保持参数形态稳定（不使用）
            "warehouse_id": int(warehouse_id),
            "item_id": int(item_id),
        }

        result = await session.execute(sql, params)
        available = result.scalar_one_or_none()
        return int(available or 0)


__all__ = ["StockAvailabilityService"]
