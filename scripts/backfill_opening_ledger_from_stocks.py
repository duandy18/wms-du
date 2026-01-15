# scripts/backfill_opening_ledger_from_stocks.py
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy import text

# ✅ 你仓库里已经有 async_session_maker fixture，通常也能 import 到这里
from app.db.session import async_session_maker


# ✅ reason 必须符合“原子动作”合同（tests/api/test_outbound_reason_contract.py）
# opening 的解释性放在 sub_reason（不参与 reason 合同校验）
OPEN_REASON = "ADJUST"
OPEN_SUB_REASON = "OPENING_BALANCE"
OPEN_REF_PREFIX = "OPEN:"


async def main() -> None:
    """
    目标：让每个 (warehouse_id,item_id,batch_code) 满足：
      SUM(stock_ledger.delta) == stocks.qty

    做法：
    - diff = stocks.qty - SUM(ledger.delta)
    - 若 diff != 0，则写入一条 opening ledger（append-only）
    - 幂等：以 (reason, ref, ref_line) 唯一，ref 设计为每个 key 唯一

    合同说明（Phase 3）：
    - baseline seed 阶段可能只写 stocks、不写 stock_ledger（部分测试要求 baseline ledger_sum == 0）
    - 因此 opening ledger 作为“解释层补账”，应在 pytest 之后执行（Makefile 已制度化）
    - 且 reason 必须保持原子（这里用 ADJUST），解释性放 sub_reason=OPENING_BALANCE
    """
    ts = datetime(1970, 1, 1, tzinfo=timezone.utc)

    async with async_session_maker() as session:
        # 1) 找出所有不一致 keys
        rows = (
            await session.execute(
                text(
                    """
                    WITH ledger_sum AS (
                      SELECT warehouse_id, item_id, batch_code, COALESCE(SUM(delta),0) AS sum_delta
                      FROM stock_ledger
                      GROUP BY warehouse_id, item_id, batch_code
                    )
                    SELECT
                      s.warehouse_id, s.item_id, s.batch_code,
                      s.qty AS stock_qty,
                      COALESCE(l.sum_delta, 0) AS ledger_qty,
                      (s.qty - COALESCE(l.sum_delta, 0)) AS diff
                    FROM stocks s
                    LEFT JOIN ledger_sum l
                      ON l.warehouse_id=s.warehouse_id
                     AND l.item_id=s.item_id
                     AND l.batch_code=s.batch_code
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

        # 2) 逐条补 opening ledger
        for r in rows:
            w = int(r["warehouse_id"])
            i = int(r["item_id"])
            b = str(r["batch_code"])
            stock_qty = int(r["stock_qty"])
            diff = int(r["diff"])

            # 对每个 key 唯一
            ref = f"{OPEN_REF_PREFIX}{w}:{i}:{b}"

            # 幂等检查：已有则跳过（以 reason/ref/ref_line 为锚点）
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
                    "batch_code": b,
                },
            )
            inserted += 1

        await session.commit()
        print(f"[opening-ledger] done: inserted={inserted} skipped={skipped}")


if __name__ == "__main__":
    asyncio.run(main())
