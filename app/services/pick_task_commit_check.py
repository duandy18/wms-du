# app/services/pick_task_commit_check.py
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.problem import raise_problem
from app.services.pick_task_loaders import load_task
from app.services.pick_task_views import get_commit_lines
from app.services.pick_task_commit_ship_apply import build_agg_from_commit_lines
from app.services.pick_task_commit_ship_apply_stock_details import shortage_detail
from app.services.pick_task_commit_ship_apply_stock_queries import load_on_hand_qty
from app.services.pick_task_commit_ship_requirements import item_requires_batch, normalize_batch_code


def _ok(*, task: Any, order_ref: str) -> Dict[str, Any]:
    return {
        "allowed": True,
        "error_code": None,
        "message": None,
        "context": {"task_id": int(task.id), "warehouse_id": int(task.warehouse_id), "ref": str(order_ref)},
        "details": [],
        "next_actions": [],
    }


async def check_commit(
    session: AsyncSession,
    *,
    task_id: int,
) -> Dict[str, Any]:
    """
    只读预检：模拟 commit_ship 的“会被硬拦”的门禁，不做任何写入/扣库。

    覆盖范围（与 apply_stock_deductions_impl 同源）：
    - empty_pick_lines（422）
    - batch_required（422）
    - insufficient_stock（409）

    注意：
    - diff_not_allowed 取决于 allow_diff 参数；主线 allow_diff=True 不作为门禁。
    - 幂等冲突/确认码等属于 commit 请求语义（trace_id/handoff_code），不在此预检。
    """
    try:
        task = await load_task(session, int(task_id), for_update=False)
    except ValueError:
        # ✅ 关键：把 “task not found” 从 500 拉回到 404 Problem（硬合同）
        raise_problem(
            status_code=404,
            error_code="pick_task_not_found",
            message="拣货任务不存在。",
            context={"task_id": int(task_id)},
            details=[{"type": "resource", "path": "task_id", "task_id": int(task_id), "reason": "not_found"}],
            next_actions=[{"action": "back_to_list", "label": "返回任务列表"}],
        )

    wh_id = int(task.warehouse_id)
    order_ref = str(task.ref or f"PICKTASK:{task.id}")

    # 1) 生成 commit 行（picked_qty>0）
    _task, commit_lines = await get_commit_lines(session, task_id=int(task.id), ignore_zero=True)
    if not commit_lines:
        return {
            "allowed": False,
            "error_code": "empty_pick_lines",
            "message": "未采集任何拣货事实，禁止提交。",
            "context": {"task_id": int(task.id), "warehouse_id": int(wh_id), "ref": str(order_ref)},
            "details": [{"type": "validation", "path": "commit_lines", "reason": "empty"}],
            "next_actions": [{"action": "continue_pick", "label": "继续拣货"}],
        }

    # 2) 聚合（item_id,batch_code）-> qty
    agg: Dict[Tuple[int, Optional[str]], int] = build_agg_from_commit_lines(commit_lines)

    # 3) 逐项预检：batch_required / insufficient_stock
    for (item_id, batch_code), total_picked in agg.items():
        need = int(total_picked or 0)
        if need <= 0:
            continue

        requires_batch = await item_requires_batch(session, item_id=int(item_id))
        bc_norm = normalize_batch_code(batch_code)

        if requires_batch and not bc_norm:
            return {
                "allowed": False,
                "error_code": "batch_required",
                "message": "批次受控商品必须提供批次，禁止提交。",
                "context": {
                    "task_id": int(task.id),
                    "warehouse_id": int(wh_id),
                    "ref": str(order_ref),
                    "item_id": int(item_id),
                },
                "details": [
                    {
                        "type": "batch",
                        "path": f"commit_lines[item_id={int(item_id)}]",
                        "item_id": int(item_id),
                        "batch_code": None,
                        "reason": "requires_batch",
                    }
                ],
                "next_actions": [
                    {"action": "edit_batch", "label": "补录/更正批次"},
                    {"action": "continue_pick", "label": "继续拣货"},
                ],
            }

        on_hand = await load_on_hand_qty(
            session,
            warehouse_id=int(wh_id),
            item_id=int(item_id),
            batch_code=bc_norm,
        )
        if int(on_hand) < int(need):
            return {
                "allowed": False,
                "error_code": "insufficient_stock",
                "message": "库存不足，禁止提交出库。",
                "context": {
                    "task_id": int(task.id),
                    "warehouse_id": int(wh_id),
                    "ref": str(order_ref),
                    "item_id": int(item_id),
                    "batch_code": bc_norm,
                },
                "details": [
                    shortage_detail(
                        item_id=int(item_id),
                        batch_code=bc_norm,
                        available_qty=int(on_hand),
                        required_qty=int(need),
                        path=f"commit_lines[item_id={int(item_id)}]",
                    )
                ],
                "next_actions": [
                    {"action": "rescan_stock", "label": "刷新库存"},
                    {"action": "adjust_to_available", "label": "按可用库存调整数量"},
                    {"action": "continue_pick", "label": "返回继续拣货/调整"},
                ],
            }

    return _ok(task=task, order_ref=order_ref)
