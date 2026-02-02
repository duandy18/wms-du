# app/services/pick_task_commit_ship.py
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import text as SA
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.problem import raise_problem
from app.services.pick_task_diff import compute_diff
from app.services.pick_task_loaders import load_task
from app.services.pick_task_views import get_commit_lines

from app.services.pick_task_commit_ship_handoff import assert_handoff_code_match
from app.services.pick_task_commit_ship_idempotency import (
    mark_task_done_inplace,
)
from app.services.pick_task_commit_ship_apply import (
    apply_stock_deductions,
    build_agg_from_commit_lines,
    write_outbound_commit_v2,
)

UTC = timezone.utc


def _raise_idempotency_conflict(*, order_ref: str, existing_trace_id: str, incoming_trace_id: str) -> None:
    raise_problem(
        status_code=409,
        error_code="idempotency_conflict",
        message="幂等冲突：该订单已提交过出库，但 trace_id 不一致，禁止重复提交。",
        context={
            "ref": str(order_ref),
            "existing_trace_id": str(existing_trace_id),
            "incoming_trace_id": str(incoming_trace_id),
        },
        details=[
            {
                "type": "idempotency",
                "path": "trace_id",
                "reason": "trace_id_mismatch",
            }
        ],
        next_actions=[
            {"action": "view_trace", "label": "查看已提交记录"},
            {"action": "rescan_order", "label": "重新扫码订单"},
        ],
    )


async def _load_outbound_commit_trace_id(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    ref: str,
) -> Optional[str]:
    """
    ✅ 唯一可信幂等证据：outbound_commits_v2
    - 不能信任 task.status=DONE（可能被历史/脏路径误写）
    """
    row = (
        await session.execute(
            SA(
                """
                SELECT trace_id
                  FROM outbound_commits_v2
                 WHERE platform = :p
                   AND shop_id  = :s
                   AND ref      = :r
                 LIMIT 1
                """
            ),
            {"p": str(platform), "s": str(shop_id), "r": str(ref)},
        )
    ).first()
    if not row:
        return None
    tid = row[0]
    return str(tid) if tid else None


async def _repair_dirty_done_if_needed(task: Any) -> bool:
    """
    脏数据纠偏（蓝皮书防御）：

    - task.status 已是 DONE（甚至 lines 也 DONE）
    - 但 outbound_commits_v2 没有记录（说明并未真正提交出库）
    - 必须把状态退回可提交态，保留 picked_qty 事实
    """
    changed = False
    if str(getattr(task, "status", "")).upper() == "DONE":
        task.status = "PICKING"
        changed = True

    lines = getattr(task, "lines", None) or []
    for ln in lines:
        if str(getattr(ln, "status", "")).upper() == "DONE":
            ln.status = "OPEN"
            changed = True

    if changed:
        now = datetime.now(UTC)
        try:
            task.updated_at = now
        except Exception:
            pass
        for ln in lines:
            try:
                ln.updated_at = now
            except Exception:
                pass
    return changed


def _build_ok_payload(
    *,
    idempotent: bool,
    task_id: int,
    warehouse_id: int,
    platform: str,
    shop_id: str,
    ref: str,
    trace_id: str,
    diff_summary: Any,
) -> Dict[str, Any]:
    """
    统一响应结构（对齐蓝皮书测试与既有 API 口径）
    """
    return {
        "status": "OK",
        "idempotent": bool(idempotent),
        "task_id": int(task_id),
        "warehouse_id": int(warehouse_id),
        "platform": str(platform),
        "shop_id": str(shop_id),
        "ref": str(ref),
        "trace_id": str(trace_id),
        "diff": {
            "task_id": int(diff_summary.task_id),
            "has_over": bool(diff_summary.has_over),
            "has_under": bool(diff_summary.has_under),
            "lines": [asdict(x) for x in diff_summary.lines],
        },
    }


async def commit_ship(
    session: AsyncSession,
    *,
    task_id: int,
    platform: str,
    shop_id: str,
    handoff_code: str,
    trace_id: Optional[str] = None,
    allow_diff: bool = True,
) -> Dict[str, Any]:
    task = await load_task(session, task_id, for_update=True)

    plat = platform.upper()
    shop = str(shop_id)
    wh_id = int(task.warehouse_id)
    order_ref = str(task.ref or f"PICKTASK:{task.id}")

    # 1) 最后扫码确认（必须 409 Problem 化）
    try:
        assert_handoff_code_match(order_ref=order_ref, handoff_code=handoff_code)
    except Exception as e:
        raise_problem(
            status_code=409,
            error_code="handoff_code_mismatch",
            message="订单核对失败（确认码不匹配），禁止提交。",
            context={
                "task_id": int(task.id),
                "warehouse_id": int(wh_id),
                "ref": str(order_ref),
            },
            details=[
                {
                    "type": "state",
                    "path": "handoff_code",
                    "reason": str(e),
                }
            ],
            next_actions=[
                {"action": "rescan_order", "label": "重新扫码订单"},
                {"action": "continue_pick", "label": "返回拣货继续检查"},
            ],
        )

    incoming_tid = (trace_id or "").strip() or None

    # 2) diff（无论是否幂等，都返回同一份 diff 结构，便于前端展示）
    diff_summary = await compute_diff(session, task_id=task.id)

    # 3) ✅ 唯一幂等证据：outbound_commits_v2
    existing_tid = await _load_outbound_commit_trace_id(session, platform=plat, shop_id=shop, ref=order_ref)

    # 3.1) 脏 DONE 纠偏：task DONE 但无 outbound_commits_v2 ⇒ 继续主线
    if existing_tid is None:
        await _repair_dirty_done_if_needed(task)

    # 3.2) outbound_commits_v2 已存在 ⇒ 幂等短路（trace_id 不一致 ⇒ 409）
    if existing_tid:
        if incoming_tid and existing_tid != incoming_tid:
            _raise_idempotency_conflict(order_ref=order_ref, existing_trace_id=existing_tid, incoming_trace_id=incoming_tid)

        now = datetime.now(UTC)
        await mark_task_done_inplace(task=task, now=now)
        await session.flush()

        return _build_ok_payload(
            idempotent=True,
            task_id=int(task.id),
            warehouse_id=int(wh_id),
            platform=plat,
            shop_id=shop,
            ref=order_ref,
            trace_id=existing_tid,
            diff_summary=diff_summary,
        )

    # 4) diff 校验（不允许欠拣/超拣时必须 422 + diffs[]）
    if not allow_diff and (diff_summary.has_over or diff_summary.has_under):
        diffs = []
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

        raise_problem(
            status_code=422,
            error_code="diff_not_allowed",
            message="欠拣/超拣不允许提交。",
            context={
                "task_id": int(task.id),
                "warehouse_id": int(wh_id),
                "ref": str(order_ref),
            },
            details=diffs or [{"type": "diff", "path": "diff", "reason": "OVER/UNDER"}],
            next_actions=[
                {"action": "continue_pick", "label": "继续拣货"},
                {"action": "void_session", "label": "作废本次拣货"},
                {"action": "go_exception_flow", "label": "转异常流程"},
            ],
        )

    # 5) 生成 commit 行（picked_qty>0）
    task, commit_lines = await get_commit_lines(session, task_id=task.id, ignore_zero=True)
    if not commit_lines:
        raise_problem(
            status_code=422,
            error_code="empty_pick_lines",
            message="未采集任何拣货事实，禁止提交。",
            context={"task_id": int(task.id), "ref": str(order_ref)},
            details=[{"type": "validation", "path": "commit_lines", "reason": "empty"}],
            next_actions=[{"action": "continue_pick", "label": "继续拣货"}],
        )

    occurred_at = datetime.now(UTC)

    # 6) 聚合 + 扣库存（库存不足会在 PickService.record_pick 内抛 409 insufficient_stock）
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

    # 7) 写 outbound_commits_v2（主线证据）
    eff_trace_id = incoming_tid or order_ref
    await write_outbound_commit_v2(
        session,
        platform=plat,
        shop_id=shop,
        ref=order_ref,
        trace_id=eff_trace_id,
    )

    # 8) DONE 终态
    now = datetime.now(UTC)
    await mark_task_done_inplace(task=task, now=now)
    await session.flush()

    return _build_ok_payload(
        idempotent=False,
        task_id=int(task.id),
        warehouse_id=int(wh_id),
        platform=plat,
        shop_id=shop,
        ref=order_ref,
        trace_id=eff_trace_id,
        diff_summary=diff_summary,
    )
