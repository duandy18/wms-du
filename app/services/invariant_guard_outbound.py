# app/services/invariant_guard_outbound.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.problem import raise_problem

UTC = timezone.utc


async def _load_touched_lot_keys_for_ref(
    session: AsyncSession,
    *,
    ref: str,
    warehouse_id: int,
    item_id: int,
    batch_code_key: str,
) -> List[int]:
    """
    从 ledger 里反推出本次 ref 实际触达的 lot_id_key 集合。
    这是 “局部可证明一致” 的关键：我们只验证本次写入触达的那批槽位。
    """
    rows = (
        await session.execute(
            text(
                """
                SELECT DISTINCT COALESCE(lot_id_key, 0) AS lot_id_key
                  FROM stock_ledger
                 WHERE ref = :ref
                   AND warehouse_id = :w
                   AND item_id = :i
                   AND batch_code_key = :ck
                """
            ),
            {"ref": str(ref), "w": int(warehouse_id), "i": int(item_id), "ck": str(batch_code_key)},
        )
    ).all()

    out: List[int] = []
    for r in rows:
        try:
            k = int(r[0] or 0)
        except Exception:
            k = 0
        if k > 0:
            out.append(k)
    return out


async def _sum_ledger_by_lot_key(
    session: AsyncSession,
    *,
    warehouse_id: int,
    item_id: int,
    lot_id_key: int,
) -> int:
    row = (
        await session.execute(
            text(
                """
                SELECT COALESCE(SUM(delta), 0)
                  FROM stock_ledger
                 WHERE warehouse_id = :w
                   AND item_id = :i
                   AND lot_id_key = :k
                """
            ),
            {"w": int(warehouse_id), "i": int(item_id), "k": int(lot_id_key)},
        )
    ).first()
    try:
        return int((row[0] if row else 0) or 0)
    except Exception:
        return 0


async def _load_stocks_lot_qty(
    session: AsyncSession,
    *,
    warehouse_id: int,
    item_id: int,
    lot_id_key: int,
) -> int:
    row = (
        await session.execute(
            text(
                """
                SELECT COALESCE(qty, 0)
                  FROM stocks_lot
                 WHERE warehouse_id = :w
                   AND item_id = :i
                   AND lot_id_key = :k
                 LIMIT 1
                """
            ),
            {"w": int(warehouse_id), "i": int(item_id), "k": int(lot_id_key)},
        )
    ).first()
    try:
        return int((row[0] if row else 0) or 0)
    except Exception:
        return 0


async def _load_touched_keys_by_ref(session: AsyncSession, *, ref: str) -> Set[Tuple[int, int, int]]:
    """
    当调用方未提供 effects 时，直接从 ledger(ref) 扫描本次触达的 (warehouse_id, item_id, lot_id_key)。
    这是 Phase 5 第二刀最实用的兼容形态：不再要求所有调用点都传 effects。
    """
    rows = (
        await session.execute(
            text(
                """
                SELECT DISTINCT warehouse_id, item_id, lot_id_key
                  FROM stock_ledger
                 WHERE ref = :ref
                   AND lot_id_key IS NOT NULL
                   AND lot_id_key > 0
                """
            ),
            {"ref": str(ref)},
        )
    ).all()

    out: Set[Tuple[int, int, int]] = set()
    for r in rows:
        try:
            w = int(r[0] or 0)
            i = int(r[1] or 0)
            k = int(r[2] or 0)
        except Exception:
            continue
        if w > 0 and i > 0 and k > 0:
            out.add((w, i, k))
    return out


async def enforce_outbound_invariant_guard(
    session: AsyncSession,
    *,
    ref: str,
    effects: Optional[Iterable[Dict[str, Any]]] = None,
    at: Optional[datetime] = None,
) -> None:
    """
    Phase 5 第一刀：执行链路不再 run_snapshot，而是做 “局部可证明一致” 校验：

    对触达的 lot_id_key 集合，验证：
        SUM(stock_ledger.delta where lot_id_key=K) == stocks_lot.qty(where lot_id_key=K)

    支持两种调用形态：
    - effects!=None：从 effects 精确反推触达集合
    - effects==None：直接从 ledger(ref) 扫描触达集合（兼容旧调用点）
    """
    debug_ref = str(ref)
    ts = at or datetime.now(UTC)

    touched: Set[Tuple[int, int, int]] = set()  # (warehouse_id, item_id, lot_id_key)

    if effects is None:
        touched = await _load_touched_keys_by_ref(session, ref=debug_ref)
    else:
        for eff in effects:
            wh_id = int(eff.get("warehouse_id") or 0)
            item_id = int(eff.get("item_id") or 0)
            ck = str(eff.get("batch_code_key") or "").strip()
            if wh_id <= 0 or item_id <= 0 or not ck:
                continue

            lot_keys = await _load_touched_lot_keys_for_ref(
                session, ref=debug_ref, warehouse_id=wh_id, item_id=item_id, batch_code_key=ck
            )
            for k in lot_keys:
                touched.add((wh_id, item_id, int(k)))

    if not touched:
        return

    mismatches: List[Dict[str, Any]] = []
    for wh_id, item_id, lot_id_key in sorted(touched):
        ledger_sum = await _sum_ledger_by_lot_key(
            session, warehouse_id=int(wh_id), item_id=int(item_id), lot_id_key=int(lot_id_key)
        )
        stocks_qty = await _load_stocks_lot_qty(
            session, warehouse_id=int(wh_id), item_id=int(item_id), lot_id_key=int(lot_id_key)
        )
        if int(ledger_sum) != int(stocks_qty):
            mismatches.append(
                {
                    "warehouse_id": int(wh_id),
                    "item_id": int(item_id),
                    "lot_id_key": int(lot_id_key),
                    "ledger_sum_delta": int(ledger_sum),
                    "stocks_lot_qty": int(stocks_qty),
                }
            )

    if mismatches:
        raise_problem(
            status_code=409,
            error_code="invariant_guard_failed",
            message="执行域不变量校验失败：ledger 与 stocks_lot 不一致，禁止提交。",
            context={"ref": debug_ref, "at": ts.isoformat()},
            details=mismatches,
            next_actions=[{"action": "reconcile", "label": "运行对账/修复"}],
        )
