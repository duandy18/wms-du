from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class PutawayService:
    """
    上架 / 搬运服务（SQL 路径 · 强契约）
    - 直接基于 stocks 扣减/增加；
    - 显式写入 stock_ledger（含 item_id / ref_line / occurred_at / after_qty）；
    - 幂等：若已存在 (reason, ref, ref_line) 或右腿(ref_line+1) 台账，则认为 idempotent；
    - “右腿 +1”：入库腿 ref_line = 出库腿 ref_line + 1；
    - 并发批量：在 PostgreSQL 用 FOR UPDATE SKIP LOCKED；SQLite 退化为无锁选择 + 乐观更新。
    - 对齐 stocks 正式口径：(item_id, warehouse_id, location_id, batch_code)
    """

    @staticmethod
    async def putaway(
        session: AsyncSession,
        *,
        item_id: int,
        from_location_id: int,
        to_location_id: int,
        qty: int,
        warehouse_id: int,
        batch_code: str,
        ref: str,
        ref_line: int = 1,
        occurred_at: datetime | None = None,
        commit: bool = True,
    ) -> dict[str, Any]:
        """
        把库存从 from_location_id → to_location_id
        扣源位、增目标位，并写两条台账（左/右腿）。
        对齐 stocks 唯一口径：item_id, warehouse_id, location_id, batch_code
        """
        if qty <= 0:
            raise ValueError("qty must be > 0")
        if from_location_id == to_location_id:
            return {"status": "noop", "moved": 0}

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
            warehouse_id=warehouse_id,
            batch_code=batch_code,
            reason="PUTAWAY",
            ref=ref,
            ref_line=ref_line,
            occurred_at=occurred_at,
        )
        if commit:
            await session.commit()
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
        commit_each: bool = True,
    ) -> dict[str, Any]:
        """
        从“暂存位/分拣位”批量搬运到目标库位：
        - PG: 以 SKIP LOCKED 逐条领取；
        - SQLite: 无锁选择 + 乐观更新（失败则跳过）。
        对齐 stocks 唯一口径：item_id, warehouse_id, location_id, batch_code
        """
        dialect = session.get_bind().dialect.name
        moved = 0
        claimed = 0

        while moved < batch_size:
            if dialect == "postgresql":
                sel_sql = """
                    SELECT id, item_id, warehouse_id, batch_code, qty
                      FROM stocks
                     WHERE location_id = :stage
                       AND qty > 0
                     ORDER BY id
                     FOR UPDATE SKIP LOCKED
                     LIMIT 1
                """
            else:
                sel_sql = """
                    SELECT id, item_id, warehouse_id, batch_code, qty
                      FROM stocks
                     WHERE location_id = :stage
                       AND qty > 0
                     ORDER BY id
                     LIMIT 1
                """
            row = (await session.execute(text(sel_sql), {"stage": stage_location_id})).first()
            if not row:
                break

            stock_id = int(row[0])
            item_id = int(row[1])
            warehouse_id = int(row[2])
            batch_code = str(row[3])
            qty_available = int(row[4] or 0)

            if qty_available <= 0:
                if commit_each:
                    await session.commit()
                continue

            claimed += 1
            quota = batch_size - moved
            move_qty = min(qty_available, quota)
            if move_qty <= 0:
                if commit_each:
                    await session.commit()
                continue

            to_location_id = int(target_locator_fn(item_id))
            ref = f"BULK-{worker_id}"
            ref_line = stock_id  # 防碰撞：以 stock 行号充当“左腿行号”

            if await PutawayService._ledger_pair_exists(
                session, reason="PUTAWAY", ref=ref, ref_line=ref_line
            ):
                if commit_each:
                    await session.commit()
                continue

            try:
                await PutawayService._move_via_sql(
                    session=session,
                    item_id=item_id,
                    from_location_id=stage_location_id,
                    to_location_id=to_location_id,
                    qty=move_qty,
                    warehouse_id=warehouse_id,
                    batch_code=batch_code,
                    reason="PUTAWAY",
                    ref=ref,
                    ref_line=ref_line,
                    occurred_at=occurred_at,
                )
                moved += move_qty
                if commit_each:
                    await session.commit()
            except ValueError:
                if commit_each:
                    await session.rollback()
                continue

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
        warehouse_id: int,
        batch_code: str,
        reason: str,
        ref: str,
        ref_line: int,
        occurred_at: datetime | None = None,
    ) -> None:
        ts = occurred_at or datetime.now(UTC)

        # 1) 扣来源位 —— 对齐口径 (item_id, warehouse_id, location_id, batch_code)
        from_row = (
            await session.execute(
                text(
                    """
                    UPDATE stocks
                       SET qty = qty - :q
                     WHERE item_id      = :item
                       AND warehouse_id = :wh
                       AND location_id  = :loc
                       AND batch_code   = :bc
                       AND qty >= :q
                    RETURNING id, qty
                    """
                ),
                {"q": qty, "item": item_id, "wh": warehouse_id, "loc": from_location_id, "bc": batch_code},
            )
        ).first()
        if not from_row:
            # 源位缺行则补 0 行再扣（满足 NOT NULL 列）
            await session.execute(
                text(
                    """
                    INSERT INTO stocks (item_id, warehouse_id, location_id, batch_code, qty)
                    VALUES (:item, :wh, :loc, :bc, 0)
                    ON CONFLICT (item_id, warehouse_id, location_id, batch_code)
                    DO NOTHING
                    """
                ),
                {"item": item_id, "wh": warehouse_id, "loc": from_location_id, "bc": batch_code},
            )
            from_row = (
                await session.execute(
                    text(
                        """
                        UPDATE stocks
                           SET qty = qty - :q
                         WHERE item_id      = :item
                           AND warehouse_id = :wh
                           AND location_id  = :loc
                           AND batch_code   = :bc
                           AND qty >= :q
                        RETURNING id, qty
                        """
                    ),
                    {"q": qty, "item": item_id, "wh": warehouse_id, "loc": from_location_id, "bc": batch_code},
                )
            ).first()
            if not from_row:
                raise ValueError("库存不足，无法完成搬运（source）")

        from_stock_id, from_after = int(from_row[0]), int(from_row[1])

        # 2) 来源位台账（左腿：ref_line）
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

        # 3) 增目标位（UPSERT 累加）
        to_row = (
            await session.execute(
                text(
                    """
                    INSERT INTO stocks (item_id, warehouse_id, location_id, batch_code, qty)
                    VALUES (:item, :wh, :loc, :bc, :q)
                    ON CONFLICT (item_id, warehouse_id, location_id, batch_code)
                      DO UPDATE SET qty = stocks.qty + EXCLUDED.qty
                    RETURNING id, qty
                    """
                ),
                {"item": item_id, "wh": warehouse_id, "loc": to_location_id, "bc": batch_code, "q": qty},
            )
        ).first()
        to_stock_id, to_after = int(to_row[0]), int(to_row[1])

        # 4) 目标位台账（右腿：ref_line+1）
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
