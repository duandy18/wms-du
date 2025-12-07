from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# 假定 ORM 模型名
from app.models import Batches, Stocks


@dataclass
class Want:
    item_id: int
    warehouse_id: int
    qty: float


@dataclass
class AllocLine:
    item_id: int
    warehouse_id: int
    location_id: int
    batch_id: Optional[int]
    qty: float


class Allocator:
    """
    提供两种策略：
      - DEFAULT: 任意可用库存（可继续使用你现有的策略）
      - FEFO: 批次按 expire_at ASC 排序，近效先出
    """

    def __init__(self, session: AsyncSession):
        self.s = session

    async def allocate_fefo_in_warehouse(
        self, want: Want, *, max_hops: int = 10_000
    ) -> List[AllocLine]:
        """
        在单一仓内按 FEFO（expire_at ASC NULLS LAST）分配；返回每个来源的明细。
        要求：Stocks 需能联到 Batches 以获取 expire_at；无批次的放到最后（NULLS LAST）。
        """
        remain = want.qty
        result: List[AllocLine] = []

        # 选出该仓内、该商品的所有批次库存，按过期时间升序
        q = (
            select(
                Stocks.item_id,
                Stocks.warehouse_id,
                Stocks.location_id,
                Stocks.batch_id,
                Stocks.available.label("available"),
                Batches.expire_at,
            )
            .join(Batches, Batches.id == Stocks.batch_id, isouter=True)
            .where(
                Stocks.item_id == want.item_id,
                Stocks.warehouse_id == want.warehouse_id,
                Stocks.available > 0,
            )
            .order_by(Batches.expire_at.asc().nulls_last())
            .limit(max_hops)
            .with_for_update()  # 强一致：锁定这些候选行，直到事务结束
        )

        rows = (await self.s.execute(q)).all()
        for item_id, wh_id, loc_id, batch_id, available, _expire in rows:
            if remain <= 0:
                break
            take = float(min(available, remain))
            if take <= 0:
                continue

            # 这里不直接扣 Stocks，只负责给出分配计划；真正扣减在 ReservationLocker 里做
            result.append(
                AllocLine(
                    item_id=item_id,
                    warehouse_id=wh_id,
                    location_id=loc_id,
                    batch_id=batch_id,
                    qty=take,
                )
            )
            remain -= take

        if remain > 1e-9:
            # 不足：由上层决定是否回滚或进行跨仓策略
            raise ValueError(f"FEFO allocation shortage: need {want.qty}, got {want.qty - remain}")

        return result
