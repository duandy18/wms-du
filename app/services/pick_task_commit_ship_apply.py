# app/services/pick_task_commit_ship_apply.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy import text as SA
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.problem import raise_problem
from app.models.enums import MovementType
from app.services.stock_service import StockService

from app.services.pick_task_commit_ship_requirements import item_requires_batch, normalize_batch_code


def build_agg_from_commit_lines(commit_lines: Any) -> Dict[Tuple[int, Optional[str]], int]:
    agg: Dict[Tuple[int, Optional[str]], int] = {}
    for line in commit_lines:
        key = (int(line.item_id), (line.batch_code or None))
        agg[key] = agg.get(key, 0) + int(line.picked_qty)
    return agg


async def _load_on_hand_qty(
    session: AsyncSession,
    *,
    warehouse_id: int,
    item_id: int,
    batch_code: Optional[str],
) -> int:
    """
    读取当前库存槽位 qty（支持 NULL batch_code）。
    槽位不存在时视为 0。
    """
    row = (
        await session.execute(
            SA(
                """
                SELECT qty
                  FROM stocks
                 WHERE warehouse_id = :w
                   AND item_id      = :i
                   AND batch_code IS NOT DISTINCT FROM :c
                 LIMIT 1
                """
            ),
            {"w": int(warehouse_id), "i": int(item_id), "c": batch_code},
        )
    ).first()
    if not row:
        return 0
    try:
        return int(row[0] or 0)
    except Exception:
        return 0


def _shortage_detail(
    *,
    item_id: int,
    batch_code: Optional[str],
    available_qty: int,
    required_qty: int,
    path: str,
) -> Dict[str, Any]:
    short_qty = max(0, int(required_qty) - int(available_qty))
    return {
        "type": "shortage",
        "path": path,
        "item_id": int(item_id),
        "batch_code": batch_code,
        # ✅ 蓝皮书合同字段（必需）
        "required_qty": int(required_qty),
        "available_qty": int(available_qty),
        "short_qty": int(short_qty),
        # ✅ 兼容/同义字段（保留，便于旧用例/调试）
        "shortage_qty": int(short_qty),
        "need": int(required_qty),
        "on_hand": int(available_qty),
        "shortage": int(short_qty),
        "reason": "insufficient_stock",
    }


async def apply_stock_deductions(
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

    关键合同：
    - HTTPException(detail=Problem) 必须原样透传（避免 details/next_actions 丢失）
    - 库存不足必须 409 insufficient_stock（可行动 shortage 细节）
    - 其它未知异常统一收敛为 500 Problem（系统异常）
    - 绝不使用 “raise_problem(...) from e”（语法非法）

    语义约束（非常重要）：
    - 订单出库提交属于 SHIP 语义，落台账必须是 SHIPMENT
    - 禁止使用默认 MovementType.PICK（当前映射为 ADJUSTMENT），否则报表/审计会失真
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

        on_hand = await _load_on_hand_qty(
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
                    _shortage_detail(
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
            raise
        except ValueError as e:
            msg = str(e)
            if "insufficient stock" in msg:
                on_hand2 = await _load_on_hand_qty(
                    session,
                    warehouse_id=int(warehouse_id),
                    item_id=int(item_id),
                    batch_code=bc_norm,
                )
                raise_problem(
                    status_code=409,
                    error_code="insufficient_stock",
                    message="库存不足，提交时被并发抢占。",
                    context={
                        "task_id": int(task_id),
                        "warehouse_id": int(warehouse_id),
                        "ref": str(order_ref),
                        "item_id": int(item_id),
                        "batch_code": bc_norm,
                    },
                    details=[
                        _shortage_detail(
                            item_id=int(item_id),
                            batch_code=bc_norm,
                            available_qty=int(on_hand2),
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
                details=[{"type": "state", "path": "apply_stock_deductions", "reason": msg}],
            )
        except Exception as e:
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


async def write_outbound_commit_v2(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    ref: str,
    trace_id: str,
) -> None:
    await session.execute(
        SA(
            """
            INSERT INTO outbound_commits_v2 (
                platform,
                shop_id,
                ref,
                state,
                created_at,
                updated_at,
                trace_id
            )
            VALUES (
                :platform,
                :shop_id,
                :ref,
                'COMPLETED',
                now(),
                now(),
                :trace_id
            )
            ON CONFLICT (platform, shop_id, ref) DO NOTHING
            """
        ),
        {"platform": platform, "shop_id": shop_id, "ref": ref, "trace_id": trace_id},
    )
