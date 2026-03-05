# scripts/audit_three_books.py
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text

from app.services.snapshot_v3_service import SnapshotV3Service


def _load_session_maker():
    candidates = [
        ("app.db.session", "async_session_maker"),
        ("app.db.session", "AsyncSessionLocal"),
        ("app.db.session", "async_session_factory"),
        ("app.db.database", "async_session_maker"),
        ("app.db.database", "AsyncSessionLocal"),
    ]
    last_err: Exception | None = None
    for mod, name in candidates:
        try:
            m = __import__(mod, fromlist=[name])
            maker = getattr(m, name)
            return maker
        except Exception as e:  # noqa: BLE001
            last_err = e
    raise RuntimeError(
        "无法找到异步 Session maker。请把 scripts/audit_three_books.py 里的 candidates 改成你项目真实路径。"
    ) from last_err


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Phase 4E 三账体检：ledger_cut vs stocks_lot vs snapshot（支持按 ref/trace 定位）"
    )
    p.add_argument("--ref", dest="ref", type=str, default=None, help="仅检查某个 ref 相关的 keys")
    p.add_argument("--trace-id", dest="trace_id", type=str, default=None, help="仅检查某个 trace_id 相关的 keys")
    p.add_argument(
        "--ignore-opening",
        action="store_true",
        help="忽略 opening 解释账（sub_reason=OPENING_BALANCE），用于只看业务一致性",
    )
    p.add_argument("--limit", dest="limit", type=int, default=10, help="输出样本行数（默认 10）")
    return p.parse_args()


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


async def _load_keys_by_ref_or_trace(
    session,
    *,
    ref: Optional[str],
    trace_id: Optional[str],
    ignore_opening: bool,
) -> List[Tuple[int, int, int, str]]:
    """
    返回 keys：(warehouse_id, item_id, lot_id_key, batch_code_key)
    """
    if not ref and not trace_id:
        return []

    where = []
    params: Dict[str, Any] = {}

    if ref:
        where.append("ref = :ref")
        params["ref"] = str(ref)

    if trace_id:
        where.append("trace_id = :tid")
        params["tid"] = str(trace_id)

    if ignore_opening:
        where.append("(sub_reason IS NULL OR sub_reason <> 'OPENING_BALANCE')")

    sql = f"""
        SELECT DISTINCT warehouse_id, item_id, lot_id_key, batch_code_key
          FROM stock_ledger
         WHERE {" AND ".join(where)}
         ORDER BY warehouse_id, item_id, lot_id_key, batch_code_key
    """

    rows = (await session.execute(text(sql), params)).all()
    keys: List[Tuple[int, int, int, str]] = []
    for w, i, lk, ck in rows:
        keys.append((int(w), int(i), int(lk), str(ck)))
    return keys


def _is_bad_row(r: Dict[str, Any]) -> bool:
    ds = r.get("diff_snapshot") or 0
    dk = r.get("diff_stock") or 0
    try:
        ds_i = int(ds)
    except Exception:
        ds_i = int(float(ds))
    try:
        dk_i = int(dk)
    except Exception:
        dk_i = int(float(dk))
    return ds_i != 0 or dk_i != 0


def _format_row(r: Dict[str, Any]) -> str:
    w = int(r.get("warehouse_id") or 0)
    i = int(r.get("item_id") or 0)
    lk = int(r.get("lot_id_key") or 0)
    bc = _norm_bc(r.get("batch_code"))
    ck = r.get("batch_code_key") or _batch_key(bc)
    return (
        f"key=(wh={w}, item={i}, lot_key={lk}, batch={bc}, batch_key={ck}) "
        f"ledger={r.get('ledger_qty')} stock={r.get('stock_qty')} snapshot={r.get('snapshot_qty')} "
        f"diff_snapshot={r.get('diff_snapshot')} diff_stock={r.get('diff_stock')}"
    )


async def main() -> None:
    args = _parse_args()
    maker = _load_session_maker()

    async with maker() as session:
        now = datetime.now(timezone.utc)

        # ✅ 审计口径：先用 ledger 重算当日 snapshot（确保 snapshot 可观测）
        await SnapshotV3Service.rebuild_snapshot_from_ledger(session, snapshot_date=now)
        await session.commit()

        # keys 过滤（可选）
        keys = await _load_keys_by_ref_or_trace(
            session,
            ref=args.ref,
            trace_id=args.trace_id,
            ignore_opening=bool(args.ignore_opening),
        )
        key_set = set(keys)

        where_ledger = []
        params: Dict[str, Any] = {}
        if args.ref:
            where_ledger.append("ref = :ref")
            params["ref"] = str(args.ref)
        if args.trace_id:
            where_ledger.append("trace_id = :tid")
            params["tid"] = str(args.trace_id)
        if args.ignore_opening:
            where_ledger.append("(sub_reason IS NULL OR sub_reason <> 'OPENING_BALANCE')")

        ledger_where_sql = ""
        if where_ledger:
            ledger_where_sql = "WHERE " + " AND ".join(where_ledger)

        # Phase 4E：三账对齐（lot-world）
        # - ledger_sum: 按 (wh,item,lot_id_key,batch_code_key) 聚合
        # - stock_qty : 来自 stocks_lot（按 lot_id_key），batch_code_key 用 lots.lot_code 推导（NULL=>__NULL_BATCH__）
        # - snapshot  : 来自 stock_snapshots（batch_code_key 为生成列）
        sql = f"""
        WITH ledger_sum AS (
          SELECT
            warehouse_id,
            item_id,
            lot_id_key,
            batch_code_key,
            COALESCE(SUM(delta), 0) AS ledger_qty
          FROM stock_ledger
          {ledger_where_sql}
          GROUP BY warehouse_id, item_id, lot_id_key, batch_code_key
        ),
        stock_slots AS (
          SELECT
            sl.warehouse_id,
            sl.item_id,
            sl.lot_id_key,
            lo.lot_code AS batch_code,
            COALESCE(lo.lot_code, '__NULL_BATCH__') AS batch_code_key,
            COALESCE(SUM(sl.qty), 0) AS stock_qty
          FROM stocks_lot sl
          LEFT JOIN lots lo ON lo.id = sl.lot_id
          GROUP BY sl.warehouse_id, sl.item_id, sl.lot_id_key, lo.lot_code
        ),
        snap_sum AS (
          SELECT
            warehouse_id,
            item_id,
            batch_code_key,
            COALESCE(SUM(qty), 0) AS snapshot_qty
          FROM stock_snapshots
          WHERE snapshot_date = (now() at time zone 'utc')::date
          GROUP BY warehouse_id, item_id, batch_code_key
        ),
        keys AS (
          SELECT warehouse_id, item_id, lot_id_key, batch_code_key FROM ledger_sum
          UNION
          SELECT warehouse_id, item_id, lot_id_key, batch_code_key FROM stock_slots
        )
        SELECT
          k.warehouse_id,
          k.item_id,
          k.lot_id_key,
          s.batch_code,
          k.batch_code_key,
          COALESCE(l.ledger_qty, 0) AS ledger_qty,
          COALESCE(s.stock_qty, 0)  AS stock_qty,
          COALESCE(sn.snapshot_qty, 0) AS snapshot_qty,
          (COALESCE(sn.snapshot_qty, 0) - COALESCE(l.ledger_qty, 0)) AS diff_snapshot,
          (COALESCE(s.stock_qty, 0) - COALESCE(l.ledger_qty, 0)) AS diff_stock
        FROM keys k
        LEFT JOIN ledger_sum l
          ON l.warehouse_id = k.warehouse_id
         AND l.item_id = k.item_id
         AND l.lot_id_key = k.lot_id_key
         AND l.batch_code_key = k.batch_code_key
        LEFT JOIN stock_slots s
          ON s.warehouse_id = k.warehouse_id
         AND s.item_id = k.item_id
         AND s.lot_id_key = k.lot_id_key
         AND s.batch_code_key = k.batch_code_key
        LEFT JOIN snap_sum sn
          ON sn.warehouse_id = k.warehouse_id
         AND sn.item_id = k.item_id
         AND sn.batch_code_key = k.batch_code_key
        ORDER BY ABS((COALESCE(s.stock_qty,0) - COALESCE(l.ledger_qty,0))) DESC
        """

        rows = (await session.execute(text(sql), params)).mappings().all()
        out = [dict(r) for r in rows]

        if key_set:
            out = [r for r in out if (int(r["warehouse_id"]), int(r["item_id"]), int(r["lot_id_key"]), str(r["batch_code_key"])) in key_set]

        bad = [r for r in out if _is_bad_row(r)]
        if bad:
            limit = max(1, int(args.limit or 10))
            sample = bad[:limit]
            lines = "\n".join(_format_row(r) for r in sample)
            raise SystemExit(f"[audit-three-books] mismatch: rows={len(bad)}\n{lines}")

        print("[audit-three-books] OK")


if __name__ == "__main__":
    asyncio.run(main())
