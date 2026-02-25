# app/services/three_books_consistency.py
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Any, Dict, List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _norm_bc(v: Any) -> str | None:
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


def _batch_key(bc: str | None) -> str:
    return bc if bc is not None else "__NULL_BATCH__"


async def verify_commit_three_books(
    session: AsyncSession,
    *,
    warehouse_id: int,
    ref: str,
    effects: List[Dict[str, Any]],
    at: datetime,
) -> None:
    """
    Phase 4C 收尾版三账校验：

    ✅ ledger 仍是唯一事实：
      - 校验每个 ref_line 的 ledger 行存在且 delta 匹配（必要条件）

    ✅ 4C 主余额切换为 stocks_lot：
      - 余额对齐：snapshot(today) 总量 == stocks_lot 总量（仅 touched items；同仓）

    说明：
    - 仍按 (warehouse_id,item_id) 做总量对齐，避免 batch_code_key/展示码漂移造成误判。
    """
    if not effects:
        return

    snap_date: date = at.date()

    # 1) ledger 存在性 + delta 校验（保持原行为：按 batch_code_key 锚定）
    missing_ledger: List[Dict[str, Any]] = []
    delta_mismatch: List[Dict[str, Any]] = []

    for e in effects:
        rl = int(e["ref_line"])
        iid = int(e["item_id"])
        bc = _norm_bc(e.get("batch_code"))
        ck = _batch_key(bc)
        qty = int(e["qty"])
        reason = e.get("reason")

        if reason is not None and str(reason).strip():
            row = (
                await session.execute(
                    text(
                        """
                        SELECT delta
                          FROM stock_ledger
                         WHERE warehouse_id   = :w
                           AND item_id        = :i
                           AND batch_code_key = :ck
                           AND ref            = :ref
                           AND ref_line       = :rl
                           AND reason         = :reason
                         LIMIT 1
                        """
                    ),
                    {
                        "w": int(warehouse_id),
                        "i": iid,
                        "ck": ck,
                        "ref": str(ref),
                        "rl": rl,
                        "reason": str(reason),
                    },
                )
            ).first()
        else:
            row = (
                await session.execute(
                    text(
                        """
                        SELECT delta
                          FROM stock_ledger
                         WHERE warehouse_id   = :w
                           AND item_id        = :i
                           AND batch_code_key = :ck
                           AND ref            = :ref
                           AND ref_line       = :rl
                         LIMIT 1
                        """
                    ),
                    {"w": int(warehouse_id), "i": iid, "ck": ck, "ref": str(ref), "rl": rl},
                )
            ).first()

        if not row:
            miss = {"item_id": iid, "batch_code": bc, "ref": ref, "ref_line": rl}
            if reason is not None and str(reason).strip():
                miss["reason"] = str(reason)
            missing_ledger.append(miss)
            continue

        delta_val = int(row[0] or 0)
        if delta_val != qty:
            mm = {
                "item_id": iid,
                "batch_code": bc,
                "ref": ref,
                "ref_line": rl,
                "expected_delta": qty,
                "ledger_delta": delta_val,
            }
            if reason is not None and str(reason).strip():
                mm["reason"] = str(reason)
            delta_mismatch.append(mm)

    if missing_ledger or delta_mismatch:
        raise ValueError(
            "三账一致性失败：ledger 写入不完整或 delta 不匹配："
            f" missing={missing_ledger} mismatch={delta_mismatch}"
        )

    # 2) touched items（只对 touched items 做余额一致性校验）
    touched_items: List[int] = sorted({int(e["item_id"]) for e in effects})
    if not touched_items:
        return

    # 3) stocks_lot 总量（同仓 + touched items）
    lot_rows = (
        await session.execute(
            text(
                """
                SELECT item_id, COALESCE(SUM(qty), 0) AS qty
                  FROM stocks_lot
                 WHERE warehouse_id = :w
                   AND item_id = ANY(:item_ids)
                 GROUP BY item_id
                 ORDER BY item_id
                """
            ),
            {"w": int(warehouse_id), "item_ids": touched_items},
        )
    ).mappings().all()
    lot_total: Dict[int, int] = {int(r["item_id"]): int(r["qty"] or 0) for r in lot_rows}
    for iid in touched_items:
        lot_total.setdefault(int(iid), 0)

    # 4) snapshot 总量（同日 + 同仓 + touched items）
    snap_rows = (
        await session.execute(
            text(
                """
                SELECT item_id, COALESCE(SUM(qty), 0) AS qty
                  FROM stock_snapshots
                 WHERE snapshot_date = :d
                   AND warehouse_id = :w
                   AND item_id = ANY(:item_ids)
                 GROUP BY item_id
                 ORDER BY item_id
                """
            ),
            {"d": snap_date, "w": int(warehouse_id), "item_ids": touched_items},
        )
    ).mappings().all()
    snap_total: Dict[int, int] = {int(r["item_id"]): int(r["qty"] or 0) for r in snap_rows}
    for iid in touched_items:
        snap_total.setdefault(int(iid), 0)

    # 5) 对齐校验（总量）
    mismatches: List[Dict[str, Any]] = []
    for iid in touched_items:
        s_qty = int(lot_total.get(int(iid), 0))
        sn_qty = int(snap_total.get(int(iid), 0))
        if s_qty != sn_qty:
            mismatches.append(
                {
                    "warehouse_id": int(warehouse_id),
                    "item_id": int(iid),
                    "stocks_lot_total": s_qty,
                    "snapshot_total": sn_qty,
                    "snapshot_date": str(snap_date),
                }
            )

    if mismatches:
        expected_delta_by_item: Dict[int, int] = defaultdict(int)
        for e in effects:
            expected_delta_by_item[int(e["item_id"])] += int(e["qty"])
        raise ValueError(
            "三账一致性失败：snapshot_total != stocks_lot_total（Phase 4C：按 item 总量对齐）"
            f" mismatches={mismatches} expected_delta_by_item={dict(expected_delta_by_item)}"
        )


# 兼容旧名称
async def verify_receive_commit_three_books(
    session: AsyncSession,
    *,
    warehouse_id: int,
    ref: str,
    effects: List[Dict[str, Any]],
    at: datetime,
) -> None:
    return await verify_commit_three_books(
        session,
        warehouse_id=warehouse_id,
        ref=ref,
        effects=effects,
        at=at,
    )
