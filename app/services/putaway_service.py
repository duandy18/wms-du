# app/services/putaway_service.py
from __future__ import annotations

from typing import Callable, Dict, Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class PutawayService:
    """
    上架 / 搬运服务（SQL 路径，避开 FEFO / adjust 的限制）
    - 直接基于 stocks 扣减/增加；
    - 显式写入 stock_ledger，并包含 NOT NULL 的 ref_line；
    - 幂等：若已存在 (reason, ref, ref_line) 或 (reason, ref, ref_line+1) 台账，即判定 idempotent；
    - “右腿 +1”规则：入库腿 ref_line = 出库腿 ref_line + 1；
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
        ref_line: int = 1,  # 出库腿的 ref_line；入库腿使用 ref_line+1
    ) -> Dict[str, Any]:
        # 幂等：若已存在“出库腿”或“入库腿”台账则直接返回
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
        - 并发安全：FOR UPDATE SKIP LOCKED 锁定单行 stocks；
        - 每处理一行后 commit 释放锁，避免长事务；
        - ref 使用 BULK-<worker_id>，ref_line 使用该行 stock_id（入库腿 +1）；
        - 返回：status / claimed（处理行数）/ moved（搬运总量）。
        """
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

            claimed += 1  # 认领一行
            quota = batch_size - moved
            move_qty = min(qty_available, quota)

            to_location_id = int(target_locator_fn(item_id))
            ref = f"BULK-{worker_id}"
            ref_line = stock_id  # 出库腿用 stock_id，入库腿用 stock_id+1

            # 幂等：若已有（出库腿或入库腿）台账，跳过移动但仍提交释放锁
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
            )

            moved += move_qty
            await session.commit()  # 释放当前行的锁

        return {"status": "ok" if moved > 0 else "idle", "claimed": claimed, "moved": moved}

    # ---------- 内部：幂等查询（成对检测） ----------
    @staticmethod
    async def _ledger_pair_exists(
        session: AsyncSession, *, reason: str, ref: str, ref_line: int
    ) -> bool:
        r = await session.execute(
            text(
                """
                SELECT 1
                  FROM stock_ledger
                 WHERE reason = :reason
                   AND ref    = :ref
                   AND ref_line IN (:out_line, :in_line)     -- 出库腿 or 入库腿(右腿+1)
                 LIMIT 1
                """
            ),
            {"reason": reason, "ref": ref, "out_line": ref_line, "in_line": ref_line + 1},
        )
        return r.first() is not None

    # ---------- 内部：直写 stocks + ledger（必须写 ref_line；右腿 +1） ----------
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
        ref_line: int,  # 出库腿 ref_line；入库腿使用 ref_line+1
    ) -> None:
        """
        直接在 stocks 扣减/增加，并写两条 ledger。
        依赖约束：
          - stocks(item_id, location_id) 唯一；
          - stock_ledger(stock_id) → stocks(id) 外键；
          - stock_ledger.ref_line NOT NULL；
          - stock_ledger(reason, ref, ref_line) 唯一（因此入库腿使用 ref_line+1）。
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

        # 2) 记来源位 ledger（出库腿，使用 ref_line）
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
                "ref_line": ref_line,          # ← 出库腿 ref_line
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

        # 4) 记目标位 ledger（入库腿，使用 ref_line+1 —— “右腿 +1”）
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
                "ref_line": ref_line + 1,      # ← 入库腿 ref_line+1，避免 UQ 冲突
                "delta": qty,
                "after": to_after,
            },
        )
