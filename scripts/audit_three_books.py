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
) -> List[Tuple[int, int, str]]:
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
        SELECT DISTINCT warehouse_id, item_id, batch_code_key
          FROM stock_ledger
         WHERE {" AND ".join(where)}
         ORDER BY warehouse_id, item_id, batch_code_key
    """

    rows = (await session.execute(text(sql), params)).all()
    keys: List[Tuple[int, int, str]] = []
    for w, i, ck in rows:
        keys.append((int(w), int(i), str(ck)))
    return keys


def _key_of_row(r: Dict[str, Any]) -> Tuple[int, int, str]:
    w = int(r.get("warehouse_id") or 0)
    i = int(r.get("item_id") or 0)
    ck = r.get("batch_code_key")
    if not ck:
        bc = _norm_bc(r.get("batch_code"))
        ck = _batch_key(bc)
    return (w, i, str(ck))


def _is_bad_row(r: Dict[str, Any]) -> bool:
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
    w = int(r.get("warehouse_id") or 0)
    i = int(r.get("item_id") or 0)
    bc = _norm_bc(r.get("batch_code"))
    ck = r.get("batch_code_key") or _batch_key(bc)
    return (
        f"key=(wh={w}, item={i}, batch={bc}, batch_key={ck}) "
        f"ledger={r.get('ledger_qty')} stock={r.get('stock_qty')} snapshot={r.get('snapshot_qty')} "
        f"diff_snapshot={r.get('diff_snapshot')} diff_stock={r.get('diff_stock')}"
    )


async def main() -> None:
    args = _parse_args()
    maker = _load_session_maker()

    async with maker() as session:
        now = datetime.now(timezone.utc)

        # ✅ 审计口径：用 ledger 重算当日 snapshot（不依赖 snapshot_today 存储过程）
        await SnapshotV3Service.rebuild_snapshot_from_ledger(session, snapshot_date=now)
        await session.commit()

        res = await SnapshotV3Service.compare_snapshot(session, snapshot_date=now)

        rows: List[Dict[str, Any]] = []
        if isinstance(res, dict):
            rows = list(res.get("rows") or [])

        keys = await _load_keys_by_ref_or_trace(
            session,
            ref=args.ref,
            trace_id=args.trace_id,
            ignore_opening=bool(args.ignore_opening),
        )
        key_set = set(keys)
        if key_set:
            rows = [r for r in rows if _key_of_row(r) in key_set]

        bad = [r for r in rows if _is_bad_row(r)]
        if bad:
            limit = max(1, int(args.limit or 10))
            sample = bad[:limit]
            lines = "\n".join(_format_row(r) for r in sample)
            raise SystemExit(f"[audit-three-books] mismatch: rows={len(bad)}\n{lines}")

        print("[audit-three-books] OK")


if __name__ == "__main__":
    asyncio.run(main())
