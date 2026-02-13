# app/services/pick_task_commit_ship_apply_stock.py
from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.problem import raise_problem
from app.models.enums import MovementType
from app.services.stock_service import StockService
from app.services.pick_task_commit_ship_requirements import item_requires_batch, normalize_batch_code
from app.services.pick_task_commit_ship_apply_stock_details import shortage_detail
from app.services.pick_task_commit_ship_apply_stock_queries import load_on_hand_qty


async def apply_stock_deductions_impl(
    session: AsyncSession,
    *,
    task_id: int,
    warehouse_id: int,
    order_ref: str,
    occurred_at: datetime,
    agg: Dict[Tuple[int, Optional[str]], int],
    trace_id: Optional[str],
) -> int:
    """
    主线裁决：扣库存 + 写台账（通过 StockService.adjust）。

    关键合同（本文件负责兑现）：
    - HTTPException(detail=Problem) 必须原样透传（避免 details/next_actions 丢失）
    - 库存不足必须 409 insufficient_stock（可行动 shortage 细节）
    - 其它未知异常统一收敛为 500 Problem（系统异常）

    注意：
    - 这里不再捕获 ValueError 并做字符串判断。
      库存不足由 StockService.adjust 统一 Problem 化（见 stock_service.py），上层只需透传 HTTPException。
    """
    stock_svc = StockService()
    ref_line = 1

    for (item_id, batch_code), total_picked in agg.items():
        if total_picked <= 0:
            continue

        requires_batch = await item_requires_batch(session, item_id=int(item_id))
        bc_norm = normalize_batch_code(batch_code)

        if requires_batch and not bc_norm:
            raise_problem(
                status_code=422,
                error_code="batch_required",
                message="批次受控商品必须提供批次，禁止提交。",
                context={
                    "task_id": int(task_id),
                    "warehouse_id": int(warehouse_id),
                    "ref": str(order_ref),
                    "item_id": int(item_id),
                },
                details=[
                    {
                        "type": "batch",
                        "path": f"commit_lines[item_id={int(item_id)}]",
                        "item_id": int(item_id),
                        "batch_code": None,
                        "reason": "requires_batch",
                    }
                ],
                next_actions=[
                    {"action": "edit_batch", "label": "补录/更正批次"},
                    {"action": "continue_pick", "label": "继续拣货"},
                ],
            )

        need = int(total_picked)

        on_hand = await load_on_hand_qty(
            session,
            warehouse_id=int(warehouse_id),
            item_id=int(item_id),
            batch_code=bc_norm,
        )
        if on_hand < need:
            raise_problem(
                status_code=409,
                error_code="insufficient_stock",
                message="库存不足，禁止提交出库。",
                context={
                    "task_id": int(task_id),
                    "warehouse_id": int(warehouse_id),
                    "ref": str(order_ref),
                    "item_id": int(item_id),
                    "batch_code": bc_norm,
                },
                details=[
                    shortage_detail(
                        item_id=int(item_id),
                        batch_code=bc_norm,
                        available_qty=int(on_hand),
                        required_qty=int(need),
                        path=f"commit_lines[item_id={int(item_id)}]",
                    )
                ],
                next_actions=[
                    {"action": "rescan_stock", "label": "刷新库存"},
                    {"action": "adjust_to_available", "label": "按可用库存调整数量"},
                    {"action": "continue_pick", "label": "返回继续拣货/调整"},
                ],
            )

        try:
            await stock_svc.adjust(
                session=session,
                item_id=int(item_id),
                delta=-int(need),
                reason=MovementType.SHIPMENT,
                ref=str(order_ref),
                ref_line=int(ref_line),
                occurred_at=occurred_at,
                meta={
                    "task_id": int(task_id),
                    "warehouse_id": int(warehouse_id),
                    "item_id": int(item_id),
                    "batch_code": (bc_norm if bc_norm else None),
                    "picked_qty": int(need),
                    "source": "pick_task_commit_ship",
                },
                batch_code=bc_norm,
                production_date=None,
                expiry_date=None,
                warehouse_id=int(warehouse_id),
                trace_id=trace_id,
            )
        except HTTPException:
            # ✅ Problem 化异常原样透传（库存不足/批次不合法/其它业务拒绝）
            raise
        except Exception as e:
            # ✅ 未知异常统一收敛为 500 Problem
            raise_problem(
                status_code=500,
                error_code="pick_apply_failed",
                message="拣货扣减失败：系统异常。",
                context={
                    "task_id": int(task_id),
                    "warehouse_id": int(warehouse_id),
                    "ref": str(order_ref),
                    "item_id": int(item_id),
                    "batch_code": bc_norm,
                },
                details=[{"type": "state", "path": "apply_stock_deductions", "reason": str(e)}],
            )

        ref_line += 1

    return ref_line
