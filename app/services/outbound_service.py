# app/services/outbound_service.py
from __future__ import annotations

import asyncio
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import DBAPIError

from app.services.audit_logger import log_event


# ===== 状态机与映射 =====

class OutboundState(str, Enum):
    PAID = "PAID"
    ALLOCATED = "ALLOCATED"
    SHIPPED = "SHIPPED"
    VOID = "VOID"


_NORMALIZE_TABLE: Dict[Tuple[str, str], OutboundState] = {
    ("pdd", "PAID"): OutboundState.PAID,
    ("jd",  "PAID"): OutboundState.PAID,
    ("taobao", "WAIT_SELLER_SEND_GOODS"): OutboundState.PAID,
    ("taobao", "TRADE_CLOSED"): OutboundState.VOID,
}

def _normalize_state(platform: str, raw_state: str) -> OutboundState:
    platform = (platform or "").lower()
    raw_state = (raw_state or "").upper()
    return _NORMALIZE_TABLE.get((platform, raw_state), OutboundState.PAID)


# ===== 并发、幂等与底层操作 =====

RETRYABLE_SQLSTATES = {"40001", "40P01", "25P02"}  # 序列化失败、死锁、事务已中止

async def _advisory_lock(session: AsyncSession, key: str) -> None:
    """PG 事务级建议锁；非 PG 静默跳过。"""
    try:
        await session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": key})
    except Exception:
        return  # 非 PG 忽略


async def _ledger_entry_exists(session: AsyncSession, ref: str, item_id: int, location_id: int) -> bool:
    row = (
        await session.execute(
            text(
                """
                SELECT 1
                FROM stock_ledger sl
                JOIN stocks s ON s.id = sl.stock_id
                WHERE sl.reason='OUTBOUND' AND sl.ref=:ref
                  AND sl.item_id=:item_id AND s.location_id=:location_id
                LIMIT 1
                """
            ),
            {"ref": ref, "item_id": item_id, "location_id": location_id},
        )
    ).first()
    return row is not None


async def _get_stock_for_update(session: AsyncSession, item_id: int, location_id: int):
    return (
        await session.execute(
            text(
                """
                SELECT id, qty
                FROM stocks
                WHERE item_id=:item_id AND location_id=:location_id
                FOR UPDATE
                """
            ),
            {"item_id": item_id, "location_id": location_id},
        )
    ).first()


async def _commit_outbound_once(session: AsyncSession, ref: str, lines: List[Dict]) -> List[Dict]:
    """单次尝试：扣减库存并记账；失败由上层决定是否重试。"""
    results: List[Dict] = []
    tx_ctx = session.begin_nested() if session.in_transaction() else session.begin()
    async with tx_ctx:
        for idx, line in enumerate(lines, start=1):
            item_id = int(line["item_id"])
            location_id = int(line["location_id"])
            need = int(line["qty"])

            # 串行化 (ref,item,loc)
            await _advisory_lock(session, f"{ref}:{item_id}:{location_id}")

            # 幂等：已有该 (ref,item,loc) 记账则跳过
            if await _ledger_entry_exists(session, ref, item_id, location_id):
                results.append(
                    {"item_id": item_id, "location_id": location_id, "committed_qty": 0, "status": "IDEMPOTENT"}
                )
                continue

            srow = await _get_stock_for_update(session, item_id, location_id)
            if srow is None or int(srow.qty) < need:
                results.append(
                    {"item_id": item_id, "location_id": location_id, "committed_qty": 0, "status": "INSUFFICIENT_STOCK"}
                )
                continue

            after_qty = int(srow.qty) - need

            await session.execute(
                text("UPDATE stocks SET qty=:after WHERE id=:id"),
                {"after": after_qty, "id": srow.id},
            )
            await session.execute(
                text(
                    """
                    INSERT INTO stock_ledger(
                        stock_id, item_id, delta, after_qty, occurred_at, reason, ref, ref_line
                    )
                    VALUES (
                        :stock_id, :item_id, :delta, :after_qty, NOW(), 'OUTBOUND', :ref, :ref_line
                    )
                    """
                ),
                {"stock_id": srow.id, "item_id": item_id, "delta": -need, "after_qty": after_qty, "ref": ref, "ref_line": idx},
            )

            results.append({"item_id": item_id, "location_id": location_id, "committed_qty": need, "status": "OK"})
    return results


async def _run_with_retry(session: AsyncSession, coro_func, *args, retries: int = 5, base_delay_ms: int = 50, **kwargs):
    """对可重试 PG 错误做指数退避重试；25P02 前先回滚保存点/事务。"""
    attempt = 0
    while True:
        try:
            return await coro_func(*args, **kwargs)
        except DBAPIError as e:
            sqlstate = getattr(e.orig, "sqlstate", None)
            if sqlstate in RETRYABLE_SQLSTATES and attempt < retries:
                try:
                    await session.rollback()  # 清理 aborted/savepoint
                except Exception:
                    pass
                await asyncio.sleep((base_delay_ms * (2 ** attempt)) / 1000.0)
                attempt += 1
                continue
            raise


async def commit_outbound(session: AsyncSession, ref: str, lines: List[Dict]) -> List[Dict]:
    """带重试的扣减流程；以 ledger 为幂等依据，避免重复扣减。"""
    return await _run_with_retry(session, _commit_outbound_once, session, ref, lines)


class OutboundService:
    @staticmethod
    async def _try_commit_state(session: AsyncSession, platform: str, ref: str, state: OutboundState) -> None:
        """
        在保存点里登记 outbound_commits；失败只回滚保存点，不影响外层事务。
        关键：不要在这里调用 session.rollback()，否则会回滚外层顶层事务，导致扣减被撤销。
        """
        try:
            async with session.begin_nested():
                await session.execute(
                    text(
                        """
                        INSERT INTO outbound_commits(platform, ref, state)
                        VALUES (:p,:r,:s)
                        ON CONFLICT (platform, ref, state) DO NOTHING
                        """
                    ),
                    {"p": platform, "r": ref, "s": state.value},
                )
        except Exception:
            # 吞掉异常：begin_nested 会自动回滚到保存点，这里不要再触碰外层事务
            pass

    @staticmethod
    async def apply_event(task: Dict[str, Any], session: Optional[AsyncSession] = None) -> Optional[List[Dict]]:
        """
        平台事件 → 出库动作：
          - 顶层事务中执行：粗粒度 ref 锁 → 扣减（带重试） → ALLOCATED 登记（保存点）
          - 尾声状态登记亦在保存点内
          - 触发条件：只要携带 lines 即扣减（测试用例/烟囱事件均满足）
        """
        platform = (task.get("platform") or "").lower()
        ref = str(task.get("ref") or "")
        raw_state = str(task.get("state") or "")
        lines = task.get("lines")
        state = _normalize_state(platform, raw_state)

        log_event(
            "outbound_event_received",
            f"{platform}#{ref} -> {state}",
            extra={"platform": platform, "ref": ref, "state": state.value, "has_lines": bool(lines)},
        )

        if not session:
            return None

        results: Optional[List[Dict]] = None

        if lines:
            # 顶层事务：确保主链（锁→扣减→记账）要么全部提交，要么全部回滚
            async with session.begin():
                await _advisory_lock(session, f"ref:{ref}")
                results = await commit_outbound(session, ref, lines)
                await OutboundService._try_commit_state(session, platform, ref, OutboundState.ALLOCATED)
                log_event("outbound_committed", f"{platform}#{ref} lines={len(lines)}")

        # 尾声：登记当前状态（保存点），失败不影响主链
        await OutboundService._try_commit_state(session, platform, ref, state)
        return results


__all__ = ["commit_outbound", "OutboundService", "OutboundState"]
