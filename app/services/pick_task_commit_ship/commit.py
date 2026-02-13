# app/services/pick_task_commit_ship/commit.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

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

from app.services.pick_task_commit_ship.utils import (
    advisory_lock_outbound_commit,
    build_diff_details,
    count_temp_fact_lines,
    iso_utc,
    UTC,
)

_VALID_SCOPES = {"PROD", "DRILL"}


def _norm_scope(scope: Optional[str]) -> str:
    sc = (scope or "").strip().upper() or "PROD"
    if sc not in _VALID_SCOPES:
        raise ValueError("scope must be PROD|DRILL")
    return sc


def _normalize_platform_shop(platform: str, shop_id: str) -> tuple[str, str]:
    return platform.upper(), str(shop_id)


def _normalize_order_ref(task: Any) -> str:
    return str(task.ref or f"PICKTASK:{task.id}")


def _normalize_incoming_trace_id(trace_id: Optional[str]) -> Optional[str]:
    return (trace_id or "").strip() or None


def _maybe_validate_handoff_code(*, order_ref: str, handoff_code: Optional[str], task_id: int, warehouse_id: int) -> None:
    """
    Phase 2：确认码已废弃
    - handoff_code 缺省/为空：跳过校验（主线）
    - handoff_code 非空：仍做一致性校验（兼容旧客户端）
    """
    got_code = (str(handoff_code or "").strip() or None)
    if got_code is None:
        return

    try:
        assert_handoff_code_match(order_ref=order_ref, handoff_code=got_code)
    except Exception as e:
        if isinstance(e, HandoffCodeError):
            raise_handoff_mismatch(
                task_id=int(task_id),
                warehouse_id=int(warehouse_id),
                order_ref=str(order_ref),
                handoff_reason=str(e.reason),
                expected_handoff_code=e.expected,
                got_handoff_code=e.got,
            )
        raise_handoff_mismatch(
            task_id=int(task_id),
            warehouse_id=int(warehouse_id),
            order_ref=str(order_ref),
            handoff_reason="unknown",
            expected_handoff_code=None,
            got_handoff_code=got_code,
        )


async def _maybe_short_circuit_idempotent(
    session: AsyncSession,
    *,
    task: Any,
    scope: str,
    platform: str,
    shop_id: str,
    order_ref: str,
    incoming_tid: Optional[str],
    diff_summary: Any,
    has_temp_lines: bool,
    temp_lines_n: int,
) -> Optional[Dict[str, Any]]:
    """
    outbound_commits_v2 已存在 ⇒ 幂等短路（trace_id 不一致 ⇒ 409）
    """
    existing_meta = await load_existing_outbound_commit_meta_or_none(
        session,
        scope=scope,
        platform=platform,
        shop_id=shop_id,
        ref=order_ref,
    )
    existing_tid = str(existing_meta.get("trace_id")) if existing_meta else None

    # 脏 DONE 纠偏：task DONE 但无 outbound_commits_v2 ⇒ 继续主线
    if existing_tid is None:
        await repair_dirty_done_if_needed(task)
        return None

    if incoming_tid and existing_tid != incoming_tid:
        raise_idempotency_conflict(
            task_id=int(task.id),
            warehouse_id=int(task.warehouse_id),
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
    committed_at = iso_utc(committed_at_dt or now)

    return build_ok_payload(
        idempotent=True,
        task_id=int(task.id),
        warehouse_id=int(task.warehouse_id),
        platform=platform,
        shop_id=shop_id,
        ref=order_ref,
        trace_id=existing_tid,
        committed_at=committed_at,
        diff_summary=diff_summary,
        has_temp_lines=has_temp_lines,
        temp_lines_n=temp_lines_n,
    )


def _assert_diff_allowed(*, allow_diff: bool, diff_summary: Any, task_id: int, warehouse_id: int, order_ref: str) -> None:
    if allow_diff:
        return
    if diff_summary.has_over or diff_summary.has_under:
        diffs = build_diff_details(diff_summary)
        raise_diff_not_allowed(
            task_id=int(task_id),
            warehouse_id=int(warehouse_id),
            order_ref=str(order_ref),
            diffs=diffs,
        )


async def _load_commit_lines_or_raise(session: AsyncSession, *, task_id: int, order_ref: str):
    task, commit_lines = await get_commit_lines(session, task_id=task_id, ignore_zero=True)
    if not commit_lines:
        raise_empty_pick_lines(task_id=int(task_id), order_ref=str(order_ref))
    return task, commit_lines


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

    # ✅ scope：以 task.scope 为准；老数据可能没有该列/值，回退 PROD
    task_scope = _norm_scope(getattr(task, "scope", None))

    plat, shop = _normalize_platform_shop(platform, shop_id)
    wh_id = int(task.warehouse_id)
    order_ref = _normalize_order_ref(task)

    # ✅ 并发护栏：同一订单 ref 的提交串行（需要纳入 scope）
    await advisory_lock_outbound_commit(session, scope=task_scope, platform=plat, shop_id=shop, ref=order_ref)

    # 1) handoff（兼容校验）
    _maybe_validate_handoff_code(order_ref=order_ref, handoff_code=handoff_code, task_id=int(task.id), warehouse_id=int(wh_id))

    incoming_tid = _normalize_incoming_trace_id(trace_id)

    # 2) diff（无论是否幂等，都返回同一份 diff 结构，便于前端展示）
    diff_summary = await compute_diff(session, task_id=task.id)

    temp_lines_n = count_temp_fact_lines(task)
    has_temp_lines = temp_lines_n > 0

    # 3) 幂等短路（如已存在证据）
    idempotent_payload = await _maybe_short_circuit_idempotent(
        session,
        task=task,
        scope=task_scope,
        platform=plat,
        shop_id=shop,
        order_ref=order_ref,
        incoming_tid=incoming_tid,
        diff_summary=diff_summary,
        has_temp_lines=has_temp_lines,
        temp_lines_n=temp_lines_n,
    )
    if idempotent_payload is not None:
        return idempotent_payload

    # 4) diff 校验（不允许欠拣/超拣时必须 422 + diffs[]）
    _assert_diff_allowed(allow_diff=allow_diff, diff_summary=diff_summary, task_id=int(task.id), warehouse_id=wh_id, order_ref=order_ref)

    # 5) 生成 commit 行（picked_qty>0）
    task, commit_lines = await _load_commit_lines_or_raise(session, task_id=int(task.id), order_ref=order_ref)

    occurred_at = datetime.now(UTC)

    # 6-7) 扣库存 + 写证据（全部按 task_scope）
    agg = build_agg_from_commit_lines(commit_lines)
    await apply_stock_deductions(
        session,
        scope=task_scope,
        task_id=task.id,
        warehouse_id=wh_id,
        order_ref=order_ref,
        occurred_at=occurred_at,
        agg=agg,
        trace_id=trace_id,
    )

    eff_tid = incoming_tid or order_ref
    oc = await write_outbound_commit_v2(
        session,
        scope=task_scope,
        platform=plat,
        shop_id=shop,
        ref=order_ref,
        trace_id=eff_tid,
    )
    final_trace_id = str(oc.get("trace_id") or eff_tid)
    created_at = oc.get("created_at")
    now = datetime.now(UTC)
    committed_at = iso_utc(created_at if isinstance(created_at, datetime) else now)

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
