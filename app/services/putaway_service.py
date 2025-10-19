# app/services/putaway_service.py
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class PutawayService:
    """
    上架 / 搬运服务（SQL 路径）
    - 直接基于 stocks 扣减/增加；
    - 显式写入 stock_ledger（含 item_id / ref_line / occurred_at）；
    - 幂等：若已存在 (reason, ref, ref_line) 或右腿(ref_line+1) 台账，则认为 idempotent；
    - “右腿 +1”：入库腿 ref_line = 出库腿 ref_line + 1；
    - 并发批量：FOR UPDATE SKIP LOCKED，每处理一行后 commit 释放锁。
    """

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
        occurred_at: datetime | None = None,
    ) -> dict[str, Any]:
        if await PutawayService._ledger_pair_exists(
            session, reason="PUTAWAY", ref=ref, ref_line=ref_line
        ):
            return {"status": "idempotent", "moved": 0}
        await PutawayService._move_via_sql(
            session=session,
            item_id=item_id,
            from_location_id=from_location_id,
            to_location_id=to_location_id,
            qty=qty,
            reason="PUTAWAY",
            ref=ref,
            ref_line=ref_line,
            occurred_at=occurred_at,
        )
        return {"status": "ok", "moved": qty}

    @staticmethod
    async def bulk_putaway(
        session: AsyncSession,
        *,
        stage_location_id: int,
        target_locator_fn: Callable[[int], int],
        batch_size: int = 100,
        worker_id: str = "W1",
        occurred_at: datetime | None = None,
    ) -> dict[str, Any]:
        moved = 0
        claimed = 0
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

            claimed += 1
            quota = batch_size - moved
            move_qty = min(qty_available, quota)

            to_location_id = int(target_locator_fn(item_id))
            ref = f"BULK-{worker_id}"
            ref_line = stock_id

            if await PutawayService._ledger_pair_exists(
                session, reason="PUTAWAY", ref=ref, ref_line=ref_line
            ):
                await session.commit()
                continue

            await PutawayService._move_via_sql(
                session=session,
                item_id=item_id,
                from_location_id=stage_location_id,
                to_location_id=to_location_id,
                qty=move_qty,
                reason="PUTAWAY",
                ref=ref,
                ref_line=ref_line,
                occurred_at=occurred_at,
            )

            moved += move_qty
            await session.commit()

        return {
            "status": "ok" if moved > 0 else "idle",
            "claimed": claimed,
            "moved": moved,
        }

    @staticmethod
    async def _ledger_pair_exists(
        session: AsyncSession, *, reason: str, ref: str, ref_line: int
    ) -> bool:
        r = await session.execute(
            text(
                """
                SELECT 1 FROM stock_ledger
                WHERE reason = :reason
                  AND ref    = :ref
                  AND ref_line IN (:out_line, :in_line)
                LIMIT 1
                """
            ),
            {
                "reason": reason,
                "ref": ref,
                "out_line": ref_line,
                "in_line": ref_line + 1,
            },
        )
        return r.first() is not None

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
        occurred_at: datetime | None = None,
    ) -> None:
        ts = occurred_at or datetime.now(UTC)

        # 1) 扣来源位
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

        # 2) 来源位台账（含 item_id/occurred_at）
        await session.execute(
            text(
                """
                INSERT INTO stock_ledger (stock_id, item_id, reason, ref, ref_line, delta, after_qty, occurred_at)
                VALUES (:sid, :item, :reason, :ref, :ref_line, :delta, :after, :ts)
                """
            ),
            {
                "sid": from_stock_id,
                "item": item_id,
                "reason": reason,
                "ref": ref,
                "ref_line": ref_line,
                "delta": -qty,
                "after": from_after,
                "ts": ts,
            },
        )

        # 3) 增目标位
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

        # 4) 目标位台账（右腿 +1；含 item_id/occurred_at）
        await session.execute(
            text(
                """
                INSERT INTO stock_ledger (stock_id, item_id, reason, ref, ref_line, delta, after_qty, occurred_at)
                VALUES (:sid, :item, :reason, :ref, :ref_line, :delta, :after, :ts)
                """
            ),
            {
                "sid": to_stock_id,
                "item": item_id,
                "reason": reason,
                "ref": ref,
                "ref_line": ref_line + 1,
                "delta": qty,
                "after": to_after,
                "ts": ts,
            },
        )
