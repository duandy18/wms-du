# app/services/putaway_service.py
from __future__ import annotations

from typing import Callable, Dict, Any, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class PutawayService:
    """
    上架 / 搬运服务（避开 FEFO 与 adjust 的 ref_line 限制）：
    - 直接基于 stocks 扣减/增加；
    - 显式写入 stock_ledger，并包含 NOT NULL 的 ref_line 字段；
    - 并发批量采用 FOR UPDATE SKIP LOCKED，每处理一行后提交释放锁。
    """

    # ---------- API：单次搬运 ----------
    @staticmethod
    async def putaway(
        session: AsyncSession,
        *,
        item_id: int,
        from_location_id: int,
        to_location_id: int,
        qty: int,
        ref: str,
        ref_line: int = 1,
    ) -> Dict[str, Any]:
        """
        把 qty 从 from_location 搬到 to_location。
        直接走 SQL 路径（不依赖批次），写两条台账（必须含 ref_line）。
        """
        await PutawayService._move_via_sql(
            session=session,
            item_id=item_id,
            from_location_id=from_location_id,
            to_location_id=to_location_id,
            qty=qty,
            reason="PUTAWAY",
            ref=ref,
            ref_line=ref_line,
        )
        return {"status": "ok", "moved": qty}

    # ---------- API：批量并发搬运（SKIP LOCKED） ----------
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
        - 并发安全：FOR UPDATE SKIP LOCKED 锁定单行 stocks；
        - 每处理一行后 commit 释放锁，避免长事务；
        - ref 使用 BULK-<worker_id>，ref_line 使用该行 stock_id（稳定且可幂等）。
        """
        moved = 0

        while moved < batch_size:
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
                break

            stock_id, item_id, qty_available = int(row[0]), int(row[1]), int(row[2])
            if qty_available <= 0:
                await session.commit()
                continue

            quota = batch_size - moved
            move_qty = min(qty_available, quota)

            to_location_id = int(target_locator_fn(item_id))
            ref = f"BULK-{worker_id}"
            ref_line = stock_id  # 用行 id 作为 ref_line，稳定幂等键

            await PutawayService._move_via_sql(
                session=session,
                item_id=item_id,
                from_location_id=stage_location_id,
                to_location_id=to_location_id,
                qty=move_qty,
                reason="PUTAWAY",
                ref=ref,
                ref_line=ref_line,
            )

            moved += move_qty
            await session.commit()  # 释放当前行的锁

        return {"status": "ok" if moved > 0 else "idle", "moved": moved}

    # ---------- 内部：直写 stocks + ledger（必须写 ref_line） ----------
    @staticmethod
    async def _move_via_sql(
        session: AsyncSession,
        *,
        item_id: int,
        from_location_id: int,
        to_location_id: int,
        qty: int,
        reason: str,
        ref: str,
        ref_line: int,
    ) -> None:
        """
        直接在 stocks 扣减/增加，并写两条 ledger。
        依赖约束：
          - stocks(item_id, location_id) 唯一；
          - stock_ledger(stock_id) → stocks(id) 外键；
          - stock_ledger.ref_line NOT NULL（本函数会显式赋值）。
        """
        # 1) 扣来源位（余额判断）
        from_row = (
            await session.execute(
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
        ).first()

        if not from_row:
            # 若来源位不存在则先 upsert 为 0，再尝试扣减（仍不足则报错）
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
            from_row = (
                await session.execute(
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
            ).first()
            if not from_row:
                raise ValueError("库存不足，无法完成搬运（source）")

        from_stock_id, from_after = int(from_row[0]), int(from_row[1])

        # 2) 记来源位 ledger（必须包含 ref_line）
        await session.execute(
            text(
                """
                INSERT INTO stock_ledger (stock_id, reason, ref, ref_line, delta, after_qty)
                VALUES (:sid, :reason, :ref, :ref_line, :delta, :after)
                """
            ),
            {
                "sid": from_stock_id,
                "reason": reason,
                "ref": ref,
                "ref_line": ref_line,
                "delta": -qty,
                "after": from_after,
            },
        )

        # 3) 增目标位（UPSERT）
        to_row = (
            await session.execute(
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
        ).first()

        to_stock_id, to_after = int(to_row[0]), int(to_row[1])

        # 4) 记目标位 ledger（必须包含 ref_line）
        await session.execute(
            text(
                """
                INSERT INTO stock_ledger (stock_id, reason, ref, ref_line, delta, after_qty)
                VALUES (:sid, :reason, :ref, :ref_line, :delta, :after)
                """
            ),
            {
                "sid": to_stock_id,
                "reason": reason,
                "ref": ref,
                "ref_line": ref_line,
                "delta": qty,
                "after": to_after,
            },
        )
