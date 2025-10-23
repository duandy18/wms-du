# app/services/outbound_service.py
from __future__ import annotations

import asyncio
import time
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import DBAPIError

from app.services.audit_logger import log_event
from app.metrics import OUTB, EVENTS, LAT  # ← 指标：出库/事件/延迟


class OutboundState(str, Enum):
    PAID = "PAID"
    ALLOCATED = "ALLOCATED"
    SHIPPED = "SHIPPED"
    VOID = "VOID"


_NORMALIZE_TABLE: Dict[Tuple[str, str], OutboundState] = {
    ("pdd", "PAID"): OutboundState.PAID,
    ("jd",  "PAID"): OutboundState.PAID,
    ("taobao", "WAIT_SELLER_SEND_GOODS"): OutboundState.PAID,
    ("tmall",  "WAIT_SELLER_SEND_GOODS"): OutboundState.PAID,
    ("taobao", "TRADE_CLOSED"): OutboundState.VOID,
    ("tmall",  "TRADE_CLOSED"): OutboundState.VOID,
    ("douyin", "PAID"): OutboundState.PAID,
    ("xhs",    "PAID"): OutboundState.PAID,
}

def _normalize_state(platform: str, raw_state: str) -> OutboundState:
    platform = (platform or "").lower()
    raw_state = (raw_state or "").upper()
    return _NORMALIZE_TABLE.get((platform, raw_state), OutboundState.PAID)

def _eff_ref(ref: str, shop_id: Optional[str]) -> str:
    r = (ref or "").strip()
    s = (shop_id or "").strip()
    return f"{s}:{r}" if s else r


RETRYABLE_SQLSTATES = {"40001", "40P01", "25P02"}

async def _advisory_lock(session: AsyncSession, key: str) -> None:
    try:
        await session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": key})
    except Exception:
        return


async def _ledger_entry_exists(session: AsyncSession, ref: str, item_id: int, location_id: int) -> bool:
    row = (await session.execute(text("""
        SELECT 1
        FROM stock_ledger sl
        JOIN stocks s ON s.id = sl.stock_id
        WHERE sl.reason='OUTBOUND' AND sl.ref=:ref
          AND sl.item_id=:item_id AND s.location_id=:location_id
        LIMIT 1
    """), {"ref": ref, "item_id": item_id, "location_id": location_id})).first()
    return row is not None


async def _get_stock_for_update(session: AsyncSession, item_id: int, location_id: int):
    return (await session.execute(text("""
        SELECT id, qty
        FROM stocks
        WHERE item_id=:item_id AND location_id=:location_id
        FOR UPDATE
    """), {"item_id": item_id, "location_id": location_id})).first()


async def _commit_outbound_once(session: AsyncSession, ref: str, lines: List[Dict]) -> List[Dict]:
    """
    核心出库提交（单次尝试）：
    - 行级幂等：已存在对应 ledger 记录直接返回 IDEMPOTENT
    - 行级并发：advisory_xact_lock + FOR UPDATE
    """
    results: List[Dict] = []
    tx_ctx = session.begin_nested() if session.in_transaction() else session.begin()
    async with tx_ctx:
        for idx, line in enumerate(lines, start=1):
            item_id = int(line["item_id"])
            location_id = int(line["location_id"])
            need = int(line["qty"])

            await _advisory_lock(session, f"{ref}:{item_id}:{location_id}")

            if await _ledger_entry_exists(session, ref, item_id, location_id):
                results.append({"item_id": item_id, "location_id": location_id, "committed_qty": 0, "status": "IDEMPOTENT"})
                continue

            srow = await _get_stock_for_update(session, item_id, location_id)
            if srow is None or int(srow.qty) < need:
                results.append({"item_id": item_id, "location_id": location_id, "committed_qty": 0, "status": "INSUFFICIENT_STOCK"})
                continue

            after_qty = int(srow.qty) - need
            await session.execute(text("UPDATE stocks SET qty=:after WHERE id=:id"), {"after": after_qty, "id": srow.id})
            await session.execute(text("""
                INSERT INTO stock_ledger(
                    stock_id, item_id, delta, after_qty, occurred_at, reason, ref, ref_line
                ) VALUES (
                    :stock_id, :item_id, :delta, :after_qty, NOW(), 'OUTBOUND', :ref, :ref_line
                )
            """), {"stock_id": srow.id, "item_id": item_id, "delta": -need, "after_qty": after_qty, "ref": ref, "ref_line": idx})

            results.append({"item_id": item_id, "location_id": location_id, "committed_qty": need, "status": "OK"})
    return results


async def _run_with_retry(session: AsyncSession, coro_func, *args, retries: int = 5, base_delay_ms: int = 50, **kwargs):
    attempt = 0
    while True:
        try:
            return await coro_func(*args, **kwargs)
        except DBAPIError as e:
            sqlstate = getattr(e.orig, "sqlstate", None)
            if sqlstate in RETRYABLE_SQLSTATES and attempt < retries:
                try: await session.rollback()
                except Exception: pass
                await asyncio.sleep((base_delay_ms * (2 ** attempt)) / 1000.0)
                attempt += 1
                continue
            raise


async def commit_outbound(session: AsyncSession, ref: str, lines: List[Dict]) -> List[Dict]:
    return await _run_with_retry(session, _commit_outbound_once, session, ref, lines)


class OutboundService:
    @staticmethod
    async def _try_commit_state(session: AsyncSession, platform: str, shop_id: str, ref: str, state: OutboundState) -> None:
        """保存点登记 outbound_commits(platform, shop_id, ref, state)；失败不污染外层事务。"""
        try:
            async with session.begin_nested():
                await session.execute(text("""
                    INSERT INTO outbound_commits(platform, shop_id, ref, state)
                    VALUES (:p,:s,:r,:t)
                    ON CONFLICT (platform, shop_id, ref, state) DO NOTHING
                """), {"p": platform, "s": shop_id, "r": ref, "t": state.value})
        except Exception:
            pass  # swallow; savepoint rollback only

    @staticmethod
    async def apply_event(task: Dict[str, Any], session: Optional[AsyncSession] = None) -> Optional[List[Dict]]:
        """
        事件应用主入口：
        - 若有 lines：提交出库（ALLOCATED），记账成功后补登记最终 state
        - 若无 lines：只登记最终 state（用于 PAID/VOID 等）
        指标：
        - 出库成功：OUTB.inc(提交总件数)
        - 事件推进：EVENTS.inc(platform,shop_id,state)
        - 延迟：LAT.observe(platform,shop_id,state,处理秒)
        """
        platform = (task.get("platform") or "").lower()
        ref = str(task.get("ref") or "")
        raw_state = str(task.get("state") or "")
        lines = task.get("lines")
        shop_id = str(task.get("shop_id") or "")
        state = _normalize_state(platform, raw_state)

        log_event("outbound_event_received",
                  f"{platform}#{shop_id}:{ref} -> {state}",
                  extra={"platform": platform, "shop_id": shop_id, "ref": ref, "state": state.value, "has_lines": bool(lines)})

        if not session:
            return None

        eff_ref = _eff_ref(ref, shop_id)
        results: Optional[List[Dict]] = None
        t0 = time.perf_counter()

        if lines:
            async with session.begin():
                await _advisory_lock(session, f"ref:{eff_ref}")
                results = await commit_outbound(session, eff_ref, lines)
                # 事件推进：ALLOCATED（按状态机）
                EVENTS.labels(platform, shop_id, OutboundState.ALLOCATED.value).inc()
                await OutboundService._try_commit_state(session, platform, shop_id, eff_ref, OutboundState.ALLOCATED)
                log_event("outbound_committed", f"{platform}#{eff_ref} lines={len(lines)}")

            # 指标：按件数累加出库提交量
            committed_total = sum(int(r.get("committed_qty") or 0) for r in (results or []) if r.get("status") == "OK")
            if committed_total > 0:
                OUTB.labels(platform, shop_id).inc(committed_total)

        # 登记最终状态（PAID/SHIPPED/VOID 等）
        await OutboundService._try_commit_state(session, platform, shop_id, eff_ref, state)
        # 事件推进：最终状态 + 延迟
        EVENTS.labels(platform, shop_id, state.value).inc()
        LAT.labels(platform, shop_id, state.value).observe(time.perf_counter() - t0)

        return results


__all__ = ["commit_outbound", "OutboundService", "OutboundState"]
