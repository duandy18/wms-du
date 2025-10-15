# app/services/putaway_service.py
from __future__ import annotations

from typing import Callable, Dict, Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class PutawayService:
    """
    上架 / 搬运服务

    设计要点：
    - 单次 putaway：通过 StockService.adjust() 记两条台账（-qty / +qty），保持“右腿 +1”幂等键（reason, ref, ref_line, stock_id）。
    - 批量 bulk_putaway：从暂存位(location_id=stage)按行锁定 SKIP LOCKED 抽取一条，搬到目标位；
      每次循环只搬一条（<= batch_size），保证在多 worker 下无阻塞竞争。
    """

    # ---------- 单次搬运 ----------
    @staticmethod
    async def putaway(
        session: AsyncSession,
        *,
        item_id: int,
        from_location_id: int,
        to_location_id: int,
        qty: int,
        ref: str,
        ref_line: int,
    ) -> Dict[str, Any]:
        """
        把 qty 从 from_location 搬到 to_location。
        通过 StockService.adjust 记两条台账（PUTAWAY / -qty 与 +qty）。
        """
        # 延迟导入，避免循环依赖
        from app.services.stock_service import StockService

        svc = StockService()

        # 先扣来源位，再加目标位（同一 ref/ref_line，依靠 stock_id 区分唯一）
        await svc.adjust(
            session=session,
            item_id=item_id,
            location_id=from_location_id,
            delta=-qty,
            reason="PUTAWAY",
            ref=ref,
            ref_line=ref_line,
        )
        await svc.adjust(
            session=session,
            item_id=item_id,
            location_id=to_location_id,
            delta=qty,
            reason="PUTAWAY",
            ref=ref,
            ref_line=ref_line,
        )

        return {"status": "ok", "moved": qty}

    # ---------- 批量并发搬运（SKIP LOCKED） ----------
    @staticmethod
    async def bulk_putaway(
        session: AsyncSession,
        *,
        stage_location_id: int,
        target_locator_fn: Callable[[int], int],
        batch_size: int = 100,
        worker_id: str = "W1",
    ) -> Dict[str, Any]:
        """
        从暂存位 stage_location_id 批量搬运库存到目标库位（按 item_id 由 target_locator_fn 决定）。
        - 并发安全：用 FOR UPDATE SKIP LOCKED 锁一行 stocks 进行处理；
        - 最小侵入：仍然调用 StockService.adjust() 记账；
        - 退出条件：没有可搬条目或达到 batch_size；
        - 返回：moved 总数与状态。

        备注：
        - 该实现每轮锁一行（id 升序），将其可用 qty 全量（或切片到 batch_size 剩余额度）搬运。
        - 适合 CI/Quick 并发用例；若要产线更高吞吐，可再做批量 SELECT + 批处理。
        """
        from app.services.stock_service import StockService

        moved = 0
        svc = StockService()

        while moved < batch_size:
            # 1) 抽取一条“暂存位且 qty > 0”的库存行，行级锁 + 跳过已被其他 worker 锁住的行
            row = (
                await session.execute(
                    text(
                        """
                        SELECT id, item_id, qty
                        FROM stocks
                        WHERE location_id = :stage AND qty > 0
                        ORDER BY id
                        FOR UPDATE SKIP LOCKED
                        LIMIT 1
                        """
                    ),
                    {"stage": stage_location_id},
                )
            ).first()

            if not row:
                # 没有可搬条目，退出循环
                break

            stock_id, item_id, qty_available = int(row[0]), int(row[1]), int(row[2])

            if qty_available <= 0:
                # 理论不应出现；防御性跳过
                await session.commit()
                continue

            # 本轮能搬多少
            quota = batch_size - moved
            move_qty = min(qty_available, quota)

            # 2) 计算目标库位
            to_location_id = int(target_locator_fn(item_id))

            # 3) 记账（-stage / +target）
            #    ref 采用 BULK-<worker_id>，ref_line 采用 stock_id，确保“同一库存行重复处理”能幂等
            ref = f"BULK-{worker_id}"
            ref_line = stock_id

            await svc.adjust(
                session=session,
                item_id=item_id,
                location_id=stage_location_id,
                delta=-move_qty,
                reason="PUTAWAY",
                ref=ref,
                ref_line=ref_line,
            )
            await svc.adjust(
                session=session,
                item_id=item_id,
                location_id=to_location_id,
                delta=move_qty,
                reason="PUTAWAY",
                ref=ref,
                ref_line=ref_line,
            )

            moved += move_qty
            # 提交释放锁，让其他并发 worker 有机会拿到下一行
            await session.commit()

        return {"status": "ok" if moved > 0 else "idle", "moved": moved}
