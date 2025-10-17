from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def _advisory_lock(session: AsyncSession, key: str) -> None:
    """
    对 (ref,item,loc) 取事务级建议锁；PG 生效，SQLite 静默忽略。
    """
    try:
        await session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": key})
    except Exception:
        # 非 PG 后端（如 SQLite）无此函数，忽略即可
        return


async def _ledger_exists(session: AsyncSession, ref: str, item_id: int, location_id: int) -> bool:
    """
    幂等判定：是否已有相同 (ref,item,loc) 的 OUTBOUND 记账。
    通过 stock_ledger join stocks 以获取 location_id。
    """
    row = (
        await session.execute(
            text(
                """
                SELECT 1
                FROM stock_ledger sl
                JOIN stocks s ON s.id = sl.stock_id
                WHERE sl.reason = 'OUTBOUND'
                  AND sl.ref = :ref
                  AND sl.item_id = :item_id
                  AND s.location_id = :location_id
                LIMIT 1
                """
            ),
            {"ref": ref, "item_id": item_id, "location_id": location_id},
        )
    ).first()
    return row is not None


async def _get_stock_for_update(session: AsyncSession, item_id: int, location_id: int):
    """
    锁定库存行，获取 id 与 qty。
    """
    return (
        await session.execute(
            text(
                """
                SELECT id, qty
                FROM stocks
                WHERE item_id = :item_id AND location_id = :location_id
                FOR UPDATE
                """
            ),
            {"item_id": item_id, "location_id": location_id},
        )
    ).first()


async def commit_outbound(session: AsyncSession, ref: str, lines: list[dict]) -> list[dict]:
    """
    出库扣减 + 记账（带幂等/并发幂等保护）：
      - 幂等：若已存在 (ref,item,loc) 的 OUTBOUND 记账 -> 返回 IDEMPOTENT，不再扣减
      - 并发：对 (ref,item,loc) 取事务级建议锁，串行化并发提交
      - 不足：返回 INSUFFICIENT_STOCK（未扣减、不记账）
      - 成功：扣减 stocks.qty 并写 stock_ledger（after_qty、occurred_at NOW()）
    返回：[{ item_id, location_id, committed_qty, status }, ...]
    """
    results: list[dict] = []

    # ✅ 关键修复：根据当前会话状态选择开启保存点或新事务
    tx_ctx = session.begin_nested() if session.in_transaction() else session.begin()

    async with tx_ctx:
        for idx, line in enumerate(lines, start=1):
            item_id = int(line["item_id"])
            location_id = int(line["location_id"])
            need = int(line["qty"])

            # 并发幂等：对 (ref,item,loc) 把请求串行化（PG 有效）
            await _advisory_lock(session, f"{ref}:{item_id}:{location_id}")

            # 先做幂等判定：若已有相同 (ref,item,loc) 的 OUTBOUND 记账，直接 IDEMPOTENT
            if await _ledger_exists(session, ref, item_id, location_id):
                results.append(
                    {
                        "item_id": item_id,
                        "location_id": location_id,
                        "committed_qty": 0,
                        "status": "IDEMPOTENT",
                    }
                )
                continue

            # 锁定库存行
            srow = await _get_stock_for_update(session, item_id, location_id)
            if srow is None or int(srow.qty) < need:
                results.append(
                    {
                        "item_id": item_id,
                        "location_id": location_id,
                        "committed_qty": 0,
                        "status": "INSUFFICIENT_STOCK",
                    }
                )
                continue

            before_qty = int(srow.qty)
            after_qty = before_qty - need

            # 扣减库存
            await session.execute(
                text("UPDATE stocks SET qty = :after WHERE id = :id"),
                {"after": after_qty, "id": srow.id},
            )

            # 写记账（OUTBOUND；包含 after_qty、occurred_at=NOW()；ref_line 为 idx）
            await session.execute(
                text(
                    """
                    INSERT INTO stock_ledger(
                        stock_id, item_id, delta, after_qty, occurred_at, reason, ref, ref_line
                    )
                    VALUES (
                        :stock_id, :item_id, :delta, :after_qty, NOW(), 'OUTBOUND', :ref, :ref_line
                    )
                    """
                ),
                {
                    "stock_id": srow.id,
                    "item_id": item_id,
                    "delta": -need,
                    "after_qty": after_qty,
                    "ref": ref,
                    "ref_line": idx,
                },
            )

            results.append(
                {
                    "item_id": item_id,
                    "location_id": location_id,
                    "committed_qty": need,
                    "status": "OK",
                }
            )

    return results
