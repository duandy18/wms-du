# scripts/audit_three_books.py
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text

from app.services.snapshot_run import run_snapshot
from app.services.snapshot_v3_service import SnapshotV3Service


def _load_session_maker():
    """
    尝试加载项目内的 async session maker。
    你项目里名称/路径可能不同，这里做多候选兼容。
    """
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
        description="Phase 3 三账体检：ledger_cut vs stocks vs snapshot（支持按 ref/trace 定位）"
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


async def _load_keys_by_ref_or_trace(
    session,
    *,
    ref: Optional[str],
    trace_id: Optional[str],
    ignore_opening: bool,
) -> List[Tuple[int, int, str]]:
    """
    从 stock_ledger 中提取某个 ref/trace_id 涉及到的 keys：
      (warehouse_id, item_id, batch_code)
    用于对 compare_snapshot 结果做过滤定位。
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
        SELECT DISTINCT warehouse_id, item_id, batch_code
          FROM stock_ledger
         WHERE {" AND ".join(where)}
         ORDER BY warehouse_id, item_id, batch_code
    """

    rows = (await session.execute(text(sql), params)).all()
    keys: List[Tuple[int, int, str]] = []
    for w, i, b in rows:
        keys.append((int(w), int(i), str(b)))
    return keys


def _key_of_row(r: Dict[str, Any]) -> Tuple[int, int, str]:
    return (int(r.get("warehouse_id") or 0), int(r.get("item_id") or 0), str(r.get("batch_code") or ""))


def _is_bad_row(r: Dict[str, Any]) -> bool:
    # compare_snapshot 输出里 diff_snapshot / diff_stock 可能是 Decimal
    ds = r.get("diff_snapshot") or 0
    dk = r.get("diff_stock") or r.get("diff_stocks") or 0
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
    w, i, b = _key_of_row(r)
    ledger_qty = r.get("ledger_qty")
    stock_qty = r.get("stock_qty")
    snap_qty = r.get("snapshot_qty")
    diff_snap = r.get("diff_snapshot")
    diff_stock = r.get("diff_stock") or r.get("diff_stocks")
    return (
        f"key=(wh={w}, item={i}, batch={b}) "
        f"ledger={ledger_qty} stock={stock_qty} snapshot={snap_qty} "
        f"diff_snapshot={diff_snap} diff_stock={diff_stock}"
    )


async def main() -> None:
    args = _parse_args()
    maker = _load_session_maker()

    async with maker() as session:
        # 1) 刷新今日快照（stock_snapshots <- stocks 汇总）
        await run_snapshot(session)

        # 2) 三账对比：ledger_cut vs snapshot vs stocks
        svc = SnapshotV3Service()
        res = await svc.compare_snapshot(session, snapshot_date=datetime.now(timezone.utc))

        rows: List[Dict[str, Any]] = []
        if isinstance(res, dict):
            rows = list(res.get("rows") or [])

        # 3) 若指定 ref/trace，则先从 ledger 抓 keys，再过滤 compare rows
        keys: List[Tuple[int, int, str]] = await _load_keys_by_ref_or_trace(
            session,
            ref=args.ref,
            trace_id=args.trace_id,
            ignore_opening=bool(args.ignore_opening),
        )
        key_set = set(keys)

        if key_set:
            rows = [r for r in rows if _key_of_row(r) in key_set]

        # 4) 如果 ignore_opening：还需要在 compare 结果里把 ledger_cut 里 opening 事件的影响排除吗？
        #    目前 compare_snapshot 走的是 ledger_cut 的累计 delta（不区分 sub_reason），所以“忽略 opening”
        #    只在“定位 keys”层面生效，不会改变数学对账结果。
        #    这符合预期：ignore_opening 用来聚焦业务 keys，而不是修改事实口径。
        bad = [r for r in rows if _is_bad_row(r)]

        if bad:
            limit = max(1, int(args.limit or 10))
            sample = bad[:limit]
            header = "[audit-three-books] mismatch"
            scope = []
            if args.ref:
                scope.append(f"ref={args.ref}")
            if args.trace_id:
                scope.append(f"trace_id={args.trace_id}")
            if args.ignore_opening:
                scope.append("ignore_opening_keys=1")
            if scope:
                header += " (" + ", ".join(scope) + ")"

            lines = "\n".join(_format_row(r) for r in sample)
            raise SystemExit(f"{header}: rows={len(bad)}\n{lines}")

        print("[audit-three-books] OK")


if __name__ == "__main__":
    asyncio.run(main())
