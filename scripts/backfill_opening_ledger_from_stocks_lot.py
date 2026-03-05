# scripts/backfill_opening_ledger_from_stocks.py
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import text

from app.db.session import async_session_maker

OPEN_REASON = "ADJUST"
OPEN_SUB_REASON = "OPENING_BALANCE"
OPEN_REF_PREFIX = "OPEN:"


def _norm_bc(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        if not s or s.lower() == "none":
            return None
        return s
    s2 = str(v).strip()
    if not s2 or s2.lower() == "none":
        return None
    return s2


def _batch_key(bc: Optional[str]) -> str:
    return bc if bc is not None else "__NULL_BATCH__"


async def main() -> None:
    """
    Phase 4E 目标：让每个 (warehouse_id, item_id, lot_id_key, batch_code_key) 满足：
      SUM(stock_ledger.delta) == stocks_lot.qty

    做法：
    - diff = stocks_lot.qty - SUM(ledger.delta)
    - 若 diff != 0，则写入一条 opening ledger（append-only）
    - 幂等：以 (reason, ref, ref_line) 唯一，ref 设计为每个 key 唯一

    注意：
    - 以 lot-world 为锚：stocks_lot + (LEFT JOIN lots 得到展示码 lot_code)
    - batch_code 作为展示码 lot_code（允许 NULL）
    - ledger 的 batch_code_key / lot_id_key 是生成列：写入时只需写 batch_code/lot_id
    """
    ts = datetime(1970, 1, 1, tzinfo=timezone.utc)

    async with async_session_maker() as session:
        rows = (
            await session.execute(
                text(
                    """
                    WITH stock_slots AS (
                      SELECT
                        sl.warehouse_id,
                        sl.item_id,
                        sl.lot_id,
                        sl.lot_id_key,
                        lo.lot_code AS batch_code,
                        COALESCE(lo.lot_code, '__NULL_BATCH__') AS batch_code_key,
                        sl.qty AS stock_qty
                      FROM stocks_lot sl
                      LEFT JOIN lots lo ON lo.id = sl.lot_id
                    ),
                    ledger_sum AS (
                      SELECT
                        warehouse_id,
                        item_id,
                        lot_id_key,
                        batch_code_key,
                        COALESCE(SUM(delta), 0) AS sum_delta
                      FROM stock_ledger
                      GROUP BY warehouse_id, item_id, lot_id_key, batch_code_key
                    )
                    SELECT
                      s.warehouse_id,
                      s.item_id,
                      s.lot_id,
                      s.lot_id_key,
                      s.batch_code,
                      s.batch_code_key,
                      s.stock_qty,
                      COALESCE(l.sum_delta, 0) AS ledger_qty,
                      (s.stock_qty - COALESCE(l.sum_delta, 0)) AS diff
                    FROM stock_slots s
                    LEFT JOIN ledger_sum l
                      ON l.warehouse_id   = s.warehouse_id
                     AND l.item_id        = s.item_id
                     AND l.lot_id_key     = s.lot_id_key
                     AND l.batch_code_key = s.batch_code_key
                    WHERE (s.stock_qty - COALESCE(l.sum_delta, 0)) <> 0
                    ORDER BY ABS(s.stock_qty - COALESCE(l.sum_delta, 0)) DESC
                    """
                )
            )
        ).mappings().all()

        if not rows:
            print("[opening-ledger] OK: no diffs")
            return

        print(f"[opening-ledger] diffs={len(rows)} (show top 10):")
        for r in rows[:10]:
            print(dict(r))

        inserted = 0
        skipped = 0

        for r in rows:
            w = int(r["warehouse_id"])
            i = int(r["item_id"])
            lot_id = r.get("lot_id")
            lot_id_int = int(lot_id) if lot_id is not None else None
            lk = int(r["lot_id_key"])
            bc = _norm_bc(r.get("batch_code"))
            ck = str(r.get("batch_code_key") or _batch_key(bc))

            stock_qty = int(r["stock_qty"])
            diff = int(r["diff"])

            # 对每个 key 唯一：ref 使用 (lot_id_key, batch_code_key)，避免 None 字符串污染
            ref = f"{OPEN_REF_PREFIX}{w}:{i}:{lk}:{ck}"

            exists = (
                await session.execute(
                    text(
                        """
                        SELECT 1
                          FROM stock_ledger
                         WHERE reason = :reason
                           AND ref = :ref
                           AND ref_line = 1
                         LIMIT 1
                        """
                    ),
                    {"reason": OPEN_REASON, "ref": ref},
                )
            ).scalar_one_or_none()

            if exists is not None:
                skipped += 1
                continue

            await session.execute(
                text(
                    """
                    INSERT INTO stock_ledger (
                      reason, sub_reason, after_qty, delta,
                      occurred_at, ref, ref_line,
                      item_id, warehouse_id, batch_code,
                      lot_id,
                      created_at
                    )
                    VALUES (
                      :reason, :sub_reason, :after, :delta,
                      :occurred_at, :ref, 1,
                      :item_id, :warehouse_id, :batch_code,
                      :lot_id,
                      NOW()
                    )
                    """
                ),
                {
                    "reason": OPEN_REASON,
                    "sub_reason": OPEN_SUB_REASON,
                    "after": stock_qty,
                    "delta": diff,
                    "occurred_at": ts,
                    "ref": ref,
                    "item_id": i,
                    "warehouse_id": w,
                    "batch_code": bc,  # may be NULL
                    "lot_id": lot_id_int,  # may be NULL (lot_id_key=0)
                },
            )
            inserted += 1

        await session.commit()
        print(f"[opening-ledger] done: inserted={inserted} skipped={skipped}")


if __name__ == "__main__":
    asyncio.run(main())
