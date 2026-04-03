# app/wms/outbound/services/pick_task_commit_ship_apply_stock.py
from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy import text as SA
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.problem import raise_problem
from app.models.enums import MovementType
from app.wms.stock.services.stock_service import StockService
from app.wms.outbound.services.pick_task_commit_ship_requirements import item_requires_batch, normalize_batch_code
from app.wms.outbound.services.pick_task_commit_ship_apply_stock_details import shortage_detail
from app.wms.outbound.services.pick_task_commit_ship_apply_stock_queries import load_on_hand_qty


def _norm_lot_code_key(v: str | None) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    return s.upper()


async def _resolve_supplier_lot_id(
    session: AsyncSession,
    *,
    warehouse_id: int,
    item_id: int,
    lot_code: str,
) -> Optional[int]:
    """
    批次受控商品（展示码非空）：lot_code 视为 lots.lot_code（SUPPLIER）。

    终态：
    - SUPPLIER 批次按 lot_code_key 唯一（防漂移）
    - 找不到 lot_id 属于业务数据缺失（应提示“lot_not_found”类问题）
    """
    k = _norm_lot_code_key(lot_code)
    if not k:
        return None

    row = (
        await session.execute(
            SA(
                """
                SELECT id
                  FROM lots
                 WHERE warehouse_id = :w
                   AND item_id      = :i
                   AND lot_code_source = 'SUPPLIER'
                   AND lot_code_key = :k
                 LIMIT 1
                """
            ),
            {"w": int(warehouse_id), "i": int(item_id), "k": str(k)},
        )
    ).first()
    if not row:
        return None
    return int(row[0])


async def _pick_one_lot_for_none_code(
    session: AsyncSession,
    *,
    warehouse_id: int,
    item_id: int,
) -> Optional[tuple[int, int]]:
    """
    非批次商品（展示码为空）：终态为 INTERNAL 单例 lot。

    这里从可扣减库存中挑一个 lot（qty>0），返回 (lot_id, qty)。
    选择策略：lot_id ASC（稳定、可解释）
    """
    row = (
        await session.execute(
            SA(
                """
                SELECT s.lot_id, s.qty
                  FROM stocks_lot s
                  JOIN lots lo
                    ON lo.id = s.lot_id
                   AND lo.warehouse_id = s.warehouse_id
                   AND lo.item_id = s.item_id
                 WHERE s.warehouse_id = :w
                   AND s.item_id      = :i
                   AND lo.lot_code IS NULL
                   AND s.qty > 0
                 ORDER BY s.lot_id ASC
                 LIMIT 1
                """
            ),
            {"w": int(warehouse_id), "i": int(item_id)},
        )
    ).first()
    if not row:
        return None
    return int(row[0]), int(row[1] or 0)


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
    主线裁决：扣库存 + 写台账（通过 StockService.adjust_lot）。

    关键合同（本文件负责兑现）：
    - HTTPException(detail=Problem) 必须原样透传（避免 details/next_actions 丢失）
    - 库存不足必须 409 insufficient_stock（可行动 shortage 细节）
    - 其它未知异常统一收敛为 500 Problem（系统异常）

    Lot-World 终态要求：
    - 扣减必须落到真实 lot_id（stocks_lot 维度：warehouse_id+item_id+lot_id）
    - batch_code 仅作为展示/输入标签（= lots.lot_code），不能替代结构身份
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

        need_total = int(total_picked)

        # 只读校验（用于可行动错误提示；不参与扣减原子性裁决）
        on_hand = await load_on_hand_qty(
            session,
            warehouse_id=int(warehouse_id),
            item_id=int(item_id),
            batch_code=bc_norm,
        )
        if on_hand < need_total:
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
                        required_qty=int(need_total),
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
            # --- lot_id 解析 + 扣减 ---
            if bc_norm:
                # 批次受控：lot_code -> SUPPLIER lot_id（按 lot_code_key 唯一）
                lot_id = await _resolve_supplier_lot_id(
                    session,
                    warehouse_id=int(warehouse_id),
                    item_id=int(item_id),
                    lot_code=str(bc_norm),
                )
                if lot_id is None:
                    raise_problem(
                        status_code=422,
                        error_code="lot_not_found",
                        message="未找到对应批次的库存槽位，禁止提交。",
                        context={
                            "task_id": int(task_id),
                            "warehouse_id": int(warehouse_id),
                            "ref": str(order_ref),
                            "item_id": int(item_id),
                            "batch_code": bc_norm,
                        },
                        details=[
                            {
                                "type": "validation",
                                "path": "stock_adjust",
                                "reason": "failed to resolve lot_id from batch_code",
                            }
                        ],
                        next_actions=[
                            {"action": "rescan_stock", "label": "刷新库存"},
                            {"action": "edit_batch", "label": "更正批次"},
                        ],
                    )

                await stock_svc.adjust_lot(
                    session=session,
                    item_id=int(item_id),
                    warehouse_id=int(warehouse_id),
                    lot_id=int(lot_id),
                    delta=-int(need_total),
                    reason=MovementType.SHIPMENT,
                    ref=str(order_ref),
                    ref_line=int(ref_line),
                    occurred_at=occurred_at,
                    batch_code=bc_norm,
                    production_date=None,
                    expiry_date=None,
                    trace_id=trace_id,
                    meta={
                        "task_id": int(task_id),
                        "warehouse_id": int(warehouse_id),
                        "item_id": int(item_id),
                        "batch_code": str(bc_norm),
                        "lot_id": int(lot_id),
                        "picked_qty": int(need_total),
                        "source": "pick_task_commit_ship",
                    },
                )
                ref_line += 1
                continue

            # 非批次商品：batch_code=None（展示码为空）
            # INTERNAL 单例 lot：仍按“从可扣减库存中找一个 lot”执行（更稳健）
            remain = int(need_total)
            while remain > 0:
                pick = await _pick_one_lot_for_none_code(
                    session,
                    warehouse_id=int(warehouse_id),
                    item_id=int(item_id),
                )
                if pick is None:
                    # 理论上不会发生（前面 on_hand 已校验够），但为防“总量够但没有可扣 lot”的脏数据情况
                    raise_problem(
                        status_code=409,
                        error_code="insufficient_stock",
                        message="库存不足或槽位异常，禁止提交出库。",
                        context={
                            "task_id": int(task_id),
                            "warehouse_id": int(warehouse_id),
                            "ref": str(order_ref),
                            "item_id": int(item_id),
                            "batch_code": None,
                        },
                        details=[
                            shortage_detail(
                                item_id=int(item_id),
                                batch_code=None,
                                available_qty=int(on_hand),
                                required_qty=int(need_total),
                                path=f"commit_lines[item_id={int(item_id)}]",
                            )
                        ],
                        next_actions=[
                            {"action": "rescan_stock", "label": "刷新库存"},
                            {"action": "continue_pick", "label": "返回继续拣货/调整"},
                        ],
                    )

                lot_id, lot_qty = pick
                take = int(lot_qty) if int(lot_qty) < remain else int(remain)

                await stock_svc.adjust_lot(
                    session=session,
                    item_id=int(item_id),
                    warehouse_id=int(warehouse_id),
                    lot_id=int(lot_id),
                    delta=-int(take),
                    reason=MovementType.SHIPMENT,
                    ref=str(order_ref),
                    ref_line=int(ref_line),
                    occurred_at=occurred_at,
                    batch_code=None,
                    production_date=None,
                    expiry_date=None,
                    trace_id=trace_id,
                    meta={
                        "task_id": int(task_id),
                        "warehouse_id": int(warehouse_id),
                        "item_id": int(item_id),
                        "batch_code": None,
                        "lot_id": int(lot_id),
                        "picked_qty": int(take),
                        "source": "pick_task_commit_ship",
                    },
                )
                ref_line += 1
                remain -= int(take)

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

    return ref_line
