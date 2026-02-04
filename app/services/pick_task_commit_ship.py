# app/services/pick_task_commit_ship.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import text as SA
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.pick_task_diff import compute_diff
from app.services.pick_task_loaders import load_task
from app.services.pick_task_views import get_commit_lines

from app.services.pick_task_commit_ship_handoff import HandoffCodeError, assert_handoff_code_match
from app.services.pick_task_commit_ship_idempotency import (
    load_existing_outbound_commit_meta_or_none,
    mark_task_done_inplace,
)
from app.services.pick_task_commit_ship_apply import (
    apply_stock_deductions,
    build_agg_from_commit_lines,
    write_outbound_commit_v2,
)
from app.services.pick_task_commit_ship_dirty_repair import repair_dirty_done_if_needed
from app.services.pick_task_commit_ship_problems import (
    raise_diff_not_allowed,
    raise_empty_pick_lines,
    raise_handoff_mismatch,
    raise_idempotency_conflict,
)
from app.services.pick_task_commit_ship_response import build_ok_payload

UTC = timezone.utc


def _iso_utc(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat()


def _build_diff_details(diff_summary: Any) -> list[Dict[str, Any]]:
    diffs: list[Dict[str, Any]] = []
    for ln in diff_summary.lines:
        status = str(getattr(ln, "status", "") or "")
        if status not in ("OVER", "UNDER"):
            continue

        req_qty = int(getattr(ln, "req_qty", 0) or 0)
        picked_qty = int(getattr(ln, "picked_qty", 0) or 0)
        delta = int(getattr(ln, "delta", 0) or 0)

        detail: Dict[str, Any] = {
            "type": "diff",
            "path": f"diff[item_id={int(ln.item_id)}]",
            "item_id": int(ln.item_id),
            "req_qty": req_qty,
            "picked_qty": picked_qty,
            "reason": status,
        }
        if delta < 0:
            detail["missing_qty"] = int(-delta)
        elif delta > 0:
            detail["over_qty"] = int(delta)

        diffs.append(detail)

    return diffs


def _count_temp_fact_lines(task: Any) -> int:
    n = 0
    for ln in getattr(task, "lines", None) or []:
        try:
            if getattr(ln, "order_id", None) is None and int(getattr(ln, "picked_qty", 0) or 0) > 0:
                n += 1
        except Exception:
            continue
    return int(n)


async def _advisory_lock_outbound_commit(session: AsyncSession, *, platform: str, shop_id: str, ref: str) -> None:
    """
    事务级并发护栏：同一 (platform, shop_id, ref) 的 commit 串行化。
    这不改变任何业务概念，只是把竞态缝焊死。
    """
    key = f"outbound_commit:{platform}:{shop_id}:{ref}"
    await session.execute(SA("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": key})


async def commit_ship(
    session: AsyncSession,
    *,
    task_id: int,
    platform: str,
    shop_id: str,
    handoff_code: Optional[str],
    trace_id: Optional[str] = None,
    allow_diff: bool = True,
) -> Dict[str, Any]:
    task = await load_task(session, task_id, for_update=True)

    plat = platform.upper()
    shop = str(shop_id)
    wh_id = int(task.warehouse_id)
    order_ref = str(task.ref or f"PICKTASK:{task.id}")

    # ✅ 并发护栏：同一订单 ref 的提交串行
    await _advisory_lock_outbound_commit(session, platform=plat, shop_id=shop, ref=order_ref)

    # Phase 2：确认码已废弃
    # - handoff_code 缺省/为空：跳过校验（主线）
    # - handoff_code 非空：仍做一致性校验（兼容旧客户端）
    got_code = (str(handoff_code or "").strip() or None)
    if got_code is not None:
        try:
            assert_handoff_code_match(order_ref=order_ref, handoff_code=got_code)
        except Exception as e:
            if isinstance(e, HandoffCodeError):
                raise_handoff_mismatch(
                    task_id=int(task.id),
                    warehouse_id=int(wh_id),
                    order_ref=str(order_ref),
                    handoff_reason=str(e.reason),
                    expected_handoff_code=e.expected,
                    got_handoff_code=e.got,
                )
            raise_handoff_mismatch(
                task_id=int(task.id),
                warehouse_id=int(wh_id),
                order_ref=str(order_ref),
                handoff_reason="unknown",
                expected_handoff_code=None,
                got_handoff_code=got_code,
            )

    incoming_tid = (trace_id or "").strip() or None

    # 2) diff（无论是否幂等，都返回同一份 diff 结构，便于前端展示）
    diff_summary = await compute_diff(session, task_id=task.id)

    # 3) ✅ 幂等证据：outbound_commits_v2（用于短路 & committed_at）
    existing_meta = await load_existing_outbound_commit_meta_or_none(session, platform=plat, shop_id=shop, ref=order_ref)
    existing_tid = str(existing_meta.get("trace_id")) if existing_meta else None

    # 3.1) 脏 DONE 纠偏：task DONE 但无 outbound_commits_v2 ⇒ 继续主线
    if existing_tid is None:
        await repair_dirty_done_if_needed(task)

    temp_lines_n = _count_temp_fact_lines(task)
    has_temp_lines = temp_lines_n > 0

    # 3.2) outbound_commits_v2 已存在 ⇒ 幂等短路（trace_id 不一致 ⇒ 409）
    if existing_tid:
        if incoming_tid and existing_tid != incoming_tid:
            raise_idempotency_conflict(
                task_id=int(task.id),
                warehouse_id=int(wh_id),
                order_ref=str(order_ref),
                existing_trace_id=str(existing_tid),
                incoming_trace_id=str(incoming_tid),
            )

        now = datetime.now(UTC)
        await mark_task_done_inplace(task=task, now=now)
        await session.flush()

        committed_at_dt = None
        if existing_meta:
            ca = existing_meta.get("created_at")
            if isinstance(ca, datetime):
                committed_at_dt = ca
        committed_at = _iso_utc(committed_at_dt or now)

        return build_ok_payload(
            idempotent=True,
            task_id=int(task.id),
            warehouse_id=int(wh_id),
            platform=plat,
            shop_id=shop,
            ref=order_ref,
            trace_id=existing_tid,
            committed_at=committed_at,
            diff_summary=diff_summary,
            has_temp_lines=has_temp_lines,
            temp_lines_n=temp_lines_n,
        )

    # 4) diff 校验（不允许欠拣/超拣时必须 422 + diffs[]）
    if not allow_diff and (diff_summary.has_over or diff_summary.has_under):
        diffs = _build_diff_details(diff_summary)
        raise_diff_not_allowed(
            task_id=int(task.id),
            warehouse_id=int(wh_id),
            order_ref=str(order_ref),
            diffs=diffs,
        )

    # 5) 生成 commit 行（picked_qty>0）
    task, commit_lines = await get_commit_lines(session, task_id=task.id, ignore_zero=True)
    if not commit_lines:
        raise_empty_pick_lines(task_id=int(task.id), order_ref=str(order_ref))

    occurred_at = datetime.now(UTC)

    # 6) 聚合 + 扣库存（库存不足 / batch_required 等均在 apply 中 Problem 化）
    agg = build_agg_from_commit_lines(commit_lines)
    await apply_stock_deductions(
        session,
        task_id=task.id,
        warehouse_id=wh_id,
        order_ref=order_ref,
        occurred_at=occurred_at,
        agg=agg,
        trace_id=trace_id,
    )

    # 7) 写/回读 outbound_commits_v2（主线证据 + 并发下真相回读）
    eff_tid = incoming_tid or order_ref
    oc = await write_outbound_commit_v2(
        session,
        platform=plat,
        shop_id=shop,
        ref=order_ref,
        trace_id=eff_tid,
    )
    final_trace_id = str(oc.get("trace_id") or eff_tid)
    created_at = oc.get("created_at")
    now = datetime.now(UTC)
    committed_at = _iso_utc(created_at if isinstance(created_at, datetime) else now)

    # 8) DONE 终态
    await mark_task_done_inplace(task=task, now=now)
    await session.flush()

    return build_ok_payload(
        idempotent=False,
        task_id=int(task.id),
        warehouse_id=int(wh_id),
        platform=plat,
        shop_id=shop,
        ref=order_ref,
        trace_id=final_trace_id,
        committed_at=committed_at,
        diff_summary=diff_summary,
        has_temp_lines=has_temp_lines,
        temp_lines_n=temp_lines_n,
    )
