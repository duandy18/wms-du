# app/services/putaway_service.py
from __future__ import annotations

from typing import Callable, Dict, Any

from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession


class PutawayService:
    """
    上架 / 搬运服务（带柔性降级）：
    - 首选调用 StockService.adjust() 记账（-qty / +qty），保持账务语义一致；
    - 若因 FEFO 批次不足导致出库失败，则降级为直写 stocks + 写 ledger，不依赖批次也能搬运。
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
        ref_line: int | None = None,  # 兼容旧签名，但不会传给 StockService.adjust
    ) -> Dict[str, Any]:
        """
        把 qty 从 from_location 搬到 to_location。
        先走 StockService.adjust（-qty / +qty），若 FEFO 无批次可扣则降级直写。
        """
        # 延迟导入，避免循环依赖
        from app.services.stock_service import StockService

        svc = StockService()

        try:
            # 先扣来源位，再加目标位（幂等依赖 StockService 内部策略；此处不透传 ref_line）
            await svc.adjust(
                session=session,
                item_id=item_id,
                location_id=from_location_id,
                delta=-qty,
                reason="PUTAWAY",
                ref=ref,
            )
            await svc.adjust(
                session=session,
                item_id=item_id,
                location_id=to_location_id,
                delta=qty,
                reason="PUTAWAY",
                ref=ref,
            )
            return {"status": "ok", "moved": qty}
        except ValueError as e:
            # 典型：“库存不足，无法按 FEFO 出库” —— 转入降级路径
            return await PutawayService._fallback_move(session,
                                                       item_id=item_id,
                                                       from_location_id=from_location_id,
                                                       to_location_id=to_location_id,
                                                       qty=qty,
                                                       ref=ref)

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
        - 并发安全：FOR UPDATE SKIP LOCKED 锁一行 stocks 进行处理；
        - 首选 adjust() 记账，失败降级为直写；
        - 退出条件：没有可搬条目或达到 batch_size；
        - 每处理一行后 commit，释放行锁。
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
                # 防御性跳过（理论不应出现）
                await session.commit()
                continue

            # 本轮能搬多少
            quota = batch_size - moved
            move_qty = min(qty_available, quota)

            # 2) 目标库位
            to_location_id = int(target_locator_fn(item_id))
            ref = f"BULK-{worker_id}"

            try:
                # 3) 优先走 adjust（-stage / +target）
                await svc.adjust(
                    session=session,
                    item_id=item_id,
                    location_id=stage_location_id,
                    delta=-move_qty,
                    reason="PUTAWAY",
                    ref=ref,
                )
                await svc.adjust(
                    session=session,
                    item_id=item_id,
                    location_id=to_location_id,
                    delta=move_qty,
                    reason="PUTAWAY",
                    ref=ref,
                )
            except ValueError:
                # FEFO 无法扣减 —— 降级为直写
                await PutawayService._fallback_move(session,
                                                    item_id=item_id,
                                                    from_location_id=stage_location_id,
                                                    to_location_id=to_location_id,
                                                    qty=move_qty,
                                                    ref=ref)

            moved += move_qty
            # 提交释放锁，让其他并发 worker 有机会拿到下一行
            await session.commit()

        return {"status": "ok" if moved > 0 else "idle", "moved": moved}

    # ---------- 降级直写（不依赖批次） ----------
    @staticmethod
    async def _fallback_move(
        session: AsyncSession,
        *,
        item_id: int,
        from_location_id: int,
        to_location_id: int,
        qty: int,
        ref: str,
    ) -> Dict[str, Any]:
        """
        直接基于 stocks 做扣减/增加，并写两条台账（不包含 batch_id）。
        依赖约束：
          - stocks(item_id, location_id) 唯一；
          - stock_ledger(stock_id) → stocks(id) 外键；
        """
        # 1) 扣来源位（确保余额足够）
        res = await session.execute(
            text(
                """
                UPDATE stocks
                   SET qty = qty - :q
                 WHERE item_id = :item
                   AND location_id = :loc
                   AND qty >= :q
                RETURNING id, qty
                """
            ),
            {"q": qty, "item": item_id, "loc": from_location_id},
        )
        row = res.first()
        if not row:
            # 尝试“若不存在则先创建 0，再判断余额”
            await session.execute(
                text(
                    """
                    INSERT INTO stocks (item_id, location_id, qty)
                    VALUES (:item, :loc, 0)
                    ON CONFLICT (item_id, location_id) DO NOTHING
                    """
                ),
                {"item": item_id, "loc": from_location_id},
            )
            # 再次扣减（此时必然失败，会抛业务错误）
            res = await session.execute(
                text(
                    """
                    UPDATE stocks
                       SET qty = qty - :q
                     WHERE item_id = :item
                       AND location_id = :loc
                       AND qty >= :q
                    RETURNING id, qty
                    """
                ),
                {"q": qty, "item": item_id, "loc": from_location_id},
            )
            row = res.first()
            if not row:
                raise ValueError("库存不足，无法完成搬运（fallback）")

        from_stock_id, from_after = int(row[0]), int(row[1])

        # 2) 写来源位台账
        await session.execute(
            text(
                """
                INSERT INTO stock_ledger (stock_id, reason, ref, delta, after_qty)
                VALUES (:sid, 'PUTAWAY', :ref, :delta, :after)
                """
            ),
            {"sid": from_stock_id, "ref": ref, "delta": -qty, "after": from_after},
        )

        # 3) 增目标位（upsert）
        res2 = await session.execute(
            text(
                """
                INSERT INTO stocks (item_id, location_id, qty)
                VALUES (:item, :loc, :q)
                ON CONFLICT (item_id, location_id)
                DO UPDATE SET qty = stocks.qty + EXCLUDED.qty
                RETURNING id, qty
                """
            ),
            {"item": item_id, "loc": to_location_id, "q": qty},
        )
        to_stock_id, to_after = (int(res2.first()[0]), int(res2.first()[1]))

        # 4) 写目标位台账
        await session.execute(
            text(
                """
                INSERT INTO stock_ledger (stock_id, reason, ref, delta, after_qty)
                VALUES (:sid, 'PUTAWAY', :ref, :delta, :after)
                """
            ),
            {"sid": to_stock_id, "ref": ref, "delta": qty, "after": to_after},
        )

        return {"status": "ok", "moved": qty}
