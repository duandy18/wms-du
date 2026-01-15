# app/services/three_books_consistency.py
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Any, Dict, List, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def verify_commit_three_books(
    session: AsyncSession,
    *,
    warehouse_id: int,
    ref: str,
    effects: List[Dict[str, Any]],
    at: datetime,
) -> None:
    """
    Phase 3：对“本次 commit（入库/出库/回仓/盘点等）”做最小可判定的三账一致性验证。

    输入：
    - warehouse_id：本次校验的仓（如跨仓调用方需分组多次调用）
    - ref：本次 commit 的 ref（例如 RT-{task_id} / ORD:...）
    - effects：每一行库存影响（warehouse_id, item_id, batch_code, qty(delta), ref_line）
      约定：qty 为 delta（入库正数、出库负数、确认事件为 0）
      ✅ 可选字段：reason
        - 若 effect 中提供 reason，则 ledger 校验会以 (warehouse_id,item_id,batch_code,ref,ref_line,reason) 为硬锚点
        - 若未提供 reason，则保持兼容旧行为（不按 reason 过滤）
    - at：发生时间，用于确定 snapshot_date（按自然日）

    验证：
    1) ledger：每个 ref_line 必须存在，并且 delta 与 qty 一致
    2) snapshot(today) == stocks（只校验本次 touched keys）
    """
    if not effects:
        return

    snap_date: date = at.date()

    # 1) ledger 存在性 + delta 校验
    missing_ledger: List[Dict[str, Any]] = []
    delta_mismatch: List[Dict[str, Any]] = []

    for e in effects:
        rl = int(e["ref_line"])
        iid = int(e["item_id"])
        bc = str(e["batch_code"])
        qty = int(e["qty"])
        reason = e.get("reason")

        if reason is not None and str(reason).strip():
            row = (
                await session.execute(
                    text(
                        """
                        SELECT delta
                          FROM stock_ledger
                         WHERE warehouse_id = :w
                           AND item_id      = :i
                           AND batch_code   = :c
                           AND ref          = :ref
                           AND ref_line     = :rl
                           AND reason       = :reason
                         LIMIT 1
                        """
                    ),
                    {
                        "w": int(warehouse_id),
                        "i": iid,
                        "c": bc,
                        "ref": str(ref),
                        "rl": rl,
                        "reason": str(reason),
                    },
                )
            ).first()
        else:
            # 兼容旧调用：不按 reason 过滤（但在 ref/ref_line 被复用时可能存在歧义）
            row = (
                await session.execute(
                    text(
                        """
                        SELECT delta
                          FROM stock_ledger
                         WHERE warehouse_id = :w
                           AND item_id      = :i
                           AND batch_code   = :c
                           AND ref          = :ref
                           AND ref_line     = :rl
                         LIMIT 1
                        """
                    ),
                    {"w": int(warehouse_id), "i": iid, "c": bc, "ref": str(ref), "rl": rl},
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

    # 2) 按 key 聚合 expected qty（用于报错时解释）
    expected_by_key: Dict[Tuple[int, int, str], int] = defaultdict(int)
    touched_keys: List[Tuple[int, int, str]] = []
    for e in effects:
        key = (int(warehouse_id), int(e["item_id"]), str(e["batch_code"]))
        expected_by_key[key] += int(e["qty"])
    touched_keys = list(expected_by_key.keys())

    # 3) 读取 stocks（当前余额）
    values_sql = ", ".join([f"(:w{i}, :i{i}, :c{i})" for i in range(len(touched_keys))])
    params: Dict[str, Any] = {}
    for idx, (w, iid, bc) in enumerate(touched_keys):
        params[f"w{idx}"] = int(w)
        params[f"i{idx}"] = int(iid)
        params[f"c{idx}"] = str(bc)

    stocks_map: Dict[Tuple[int, int, str], int] = {}
    if touched_keys:
        rows = (
            await session.execute(
                text(
                    f"""
                    WITH keys(warehouse_id, item_id, batch_code) AS (
                        VALUES {values_sql}
                    )
                    SELECT s.warehouse_id, s.item_id, s.batch_code, s.qty
                      FROM keys k
                      LEFT JOIN stocks s
                        ON s.warehouse_id = k.warehouse_id
                       AND s.item_id      = k.item_id
                       AND s.batch_code   = k.batch_code
                    """
                ),
                params,
            )
        ).mappings().all()

        for r in rows:
            key = (int(r["warehouse_id"]), int(r["item_id"]), str(r["batch_code"]))
            stocks_map[key] = int(r["qty"] or 0)

    # 4) 读取 snapshot(today)
    snap_map: Dict[Tuple[int, int, str], int] = {}
    if touched_keys:
        snap_rows = (
            await session.execute(
                text(
                    f"""
                    WITH keys(warehouse_id, item_id, batch_code) AS (
                        VALUES {values_sql}
                    )
                    SELECT k.warehouse_id, k.item_id, k.batch_code, COALESCE(sn.qty_on_hand, 0) AS qty_on_hand
                      FROM keys k
                      LEFT JOIN stock_snapshots sn
                        ON sn.snapshot_date = :d
                       AND sn.warehouse_id  = k.warehouse_id
                       AND sn.item_id       = k.item_id
                       AND sn.batch_code    = k.batch_code
                    """
                ),
                {"d": snap_date, **params},
            )
        ).mappings().all()

        for r in snap_rows:
            key = (int(r["warehouse_id"]), int(r["item_id"]), str(r["batch_code"]))
            snap_map[key] = int(r["qty_on_hand"] or 0)

    # 5) 校验 snapshot == stocks（只对 touched keys）
    mismatches: List[Dict[str, Any]] = []
    for key in touched_keys:
        s_qty = int(stocks_map.get(key, 0))
        sn_qty = int(snap_map.get(key, 0))
        if s_qty != sn_qty:
            w, iid, bc = key
            mismatches.append(
                {
                    "warehouse_id": w,
                    "item_id": iid,
                    "batch_code": bc,
                    "stocks_qty": s_qty,
                    "snapshot_qty": sn_qty,
                    "expected_delta_sum": int(expected_by_key.get(key, 0)),
                    "snapshot_date": str(snap_date),
                }
            )

    if mismatches:
        raise ValueError(f"三账一致性失败：snapshot != stocks：mismatches={mismatches}")


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
