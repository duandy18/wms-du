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
    目标：让每个 (warehouse_id,item_id,batch_code_key) 满足：
      SUM(stock_ledger.delta) == stocks.qty

    做法：
    - diff = stocks.qty - SUM(ledger.delta)
    - 若 diff != 0，则写入一条 opening ledger（append-only）
    - 幂等：以 (reason, ref, ref_line) 唯一，ref 设计为每个 key 唯一

    注意：
    - join 统一走 batch_code_key（NULL 语义稳定）
    - 绝不允许把 NULL batch_code 写成字符串 "None"
    """
    ts = datetime(1970, 1, 1, tzinfo=timezone.utc)

    async with async_session_maker() as session:
        rows = (
            await session.execute(
                text(
                    """
                    WITH ledger_sum AS (
                      SELECT warehouse_id,
                             item_id,
                             batch_code_key,
                             COALESCE(SUM(delta),0) AS sum_delta
                        FROM stock_ledger
                       GROUP BY warehouse_id, item_id, batch_code_key
                    )
                    SELECT
                      s.warehouse_id,
                      s.item_id,
                      s.batch_code,
                      s.batch_code_key,
                      s.qty AS stock_qty,
                      COALESCE(l.sum_delta, 0) AS ledger_qty,
                      (s.qty - COALESCE(l.sum_delta, 0)) AS diff
                    FROM stocks s
                    LEFT JOIN ledger_sum l
                      ON l.warehouse_id   = s.warehouse_id
                     AND l.item_id        = s.item_id
                     AND l.batch_code_key = s.batch_code_key
                    WHERE (s.qty - COALESCE(l.sum_delta, 0)) <> 0
                    ORDER BY ABS(s.qty - COALESCE(l.sum_delta, 0)) DESC
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
            bc = _norm_bc(r["batch_code"])
            ck = str(r["batch_code_key"] or _batch_key(bc))

            stock_qty = int(r["stock_qty"])
            diff = int(r["diff"])

            # 对每个 key 唯一：ref 使用 batch_code_key，避免 None 字符串污染
            ref = f"{OPEN_REF_PREFIX}{w}:{i}:{ck}"

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
                      created_at
                    )
                    VALUES (
                      :reason, :sub_reason, :after, :delta,
                      :occurred_at, :ref, 1,
                      :item_id, :warehouse_id, :batch_code,
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
                    "batch_code": bc,  # ✅ may be NULL
                },
            )
            inserted += 1

        await session.commit()
        print(f"[opening-ledger] done: inserted={inserted} skipped={skipped}")


if __name__ == "__main__":
    asyncio.run(main())
