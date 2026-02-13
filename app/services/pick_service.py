# app/services/pick_service.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, Union

from sqlalchemy import text as SA
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.services.stock_service import StockService


class PickService:
    """
    v2 拣货（出库）Facade（location_id 已移除；FEFO 仅提示不刚性）：

    设计要点
    - 拣货即扣减：扫码确认后立刻扣减库存（原子 + 幂等由 StockService.adjust 保障）
    - 批次强制：仅对 requires_batch=true 的商品强制 batch_code；requires_batch=false 允许 NULL
    - 粒度统一：库存槽位最终以 (item_id, warehouse_id, batch_code|NULL) 表达
    - FEFO 柔性：不强制 FEFO，只要指定批次即可扣减；FEFO 风险通过快照/查询提示

    Phase N（订单驱动增强）：
    - 允许调用方传入 trace_id，用于将本次扣减挂到订单 trace 上；
    - trace_id 透传到 StockService.adjust → stock_ledger.trace_id；
    - 订单驱动的 HTTP 层可以从 orders.trace_id 获取该 trace_id 并传入。

    语义约束（非常重要）：
    - “扣减库存”只是动作；台账 reason 必须表达业务语义。
    - 默认：通用拣货使用 MovementType.PICK（当前映射为 ADJUSTMENT）。
    - 订单出库：调用方应显式传入 movement_type=MovementType.SHIP（落库为 SHIPMENT）。

    ✅ 本窗口演进（唯一主线）：
    - requires_batch=true  => batch_code 必填
    - requires_batch=false => batch_code 允许为 NULL（表示“无批次”，不是“未知批次”）
    """

    def __init__(self, stock_svc: Optional[StockService] = None) -> None:
        self.stock_svc = stock_svc or StockService()

    async def _item_requires_batch(self, session: AsyncSession, *, item_id: int) -> bool:
        """
        临时事实派生：
        - items.has_shelf_life == True  => requires_batch == True
        - 其他（False/NULL）            => requires_batch == False

        重要：item 不存在时不要在这里提前 raise，
        让后续写库触发 FK（测试依赖此行为）。
        """
        row = (
            await session.execute(
                SA(
                    """
                    SELECT has_shelf_life
                      FROM items
                     WHERE id = :item_id
                     LIMIT 1
                    """
                ),
                {"item_id": int(item_id)},
            )
        ).first()
        if not row:
            return False
        return bool(row[0] is True)

    async def _load_stock_qty(
        self,
        session: AsyncSession,
        *,
        warehouse_id: int,
        item_id: int,
        batch_code: Optional[str],
    ) -> int:
        """
        用于“库存不足”时给出可行动的缺口明细：
        - 这是一个只读查询，不参与扣减原子性裁决；
        - 目的是让操作员知道“缺多少”，并允许用户显式调整数量重试。

        ✅ 关键修复：
        - psycopg 对 NULL 参数类型推断敏感，`:bc IS NULL` + `batch_code=:bc` 会触发 AmbiguousParameter
        - 改为 `IS NOT DISTINCT FROM CAST(:bc AS TEXT)`，既处理 NULL，又显式类型
        """
        row = (
            await session.execute(
                SA(
                    """
                    SELECT qty
                      FROM stocks
                     WHERE warehouse_id = :wid
                       AND item_id = :item_id
                       AND batch_code IS NOT DISTINCT FROM CAST(:bc AS TEXT)
                     LIMIT 1
                    """
                ),
                {"wid": int(warehouse_id), "item_id": int(item_id), "bc": batch_code},
            )
        ).first()
        if not row:
            return 0
        try:
            return int(row[0] or 0)
        except Exception:
            return 0

    async def record_pick(
        self,
        session: AsyncSession,
        *,
        item_id: int,
        qty: int,
        ref: str,
        occurred_at: datetime,
        batch_code: Optional[str],
        warehouse_id: int,
        trace_id: Optional[str] = None,
        start_ref_line: Optional[int] = None,
        task_line_id: Optional[int] = None,
        movement_type: Union[str, MovementType] = MovementType.PICK,
    ) -> Dict[str, Any]:
        if qty <= 0:
            raise ValueError("Qty must be > 0 for pick record.")
        if warehouse_id is None or int(warehouse_id) <= 0:
            raise ValueError("拣货必须明确 warehouse_id。")

        requires_batch = await self._item_requires_batch(session, item_id=int(item_id))

        bc_norm: Optional[str]
        if batch_code is None:
            bc_norm = None
        else:
            s = str(batch_code).strip()
            bc_norm = s or None

        if requires_batch and not bc_norm:
            raise ValueError("批次受控商品扫码拣货必须提供 batch_code。")

        ref_line = int(start_ref_line or 1)

        try:
            result = await self.stock_svc.adjust(
                session=session,
                item_id=item_id,
                delta=-int(qty),
                reason=movement_type,
                ref=ref,
                ref_line=ref_line,
                occurred_at=occurred_at,
                batch_code=bc_norm,
                warehouse_id=int(warehouse_id),
                trace_id=trace_id,
            )
        except ValueError as e:
            # 统一裁决：库存不足/并发变化等 “现实不满足制度” → 409 + 可行动明细
            from app.api.problem import raise_problem

            available = await self._load_stock_qty(
                session,
                warehouse_id=int(warehouse_id),
                item_id=int(item_id),
                batch_code=bc_norm,
            )
            required = int(qty)
            short_qty = max(required - int(available), 0)

            raise_problem(
                status_code=409,
                error_code="insufficient_stock",
                message="库存已变化：当前可用量不足，无法提交出库。",
                context={
                    "warehouse_id": int(warehouse_id),
                    "item_id": int(item_id),
                    "batch_code": bc_norm,
                    "ref": str(ref),
                    "ref_line": int(ref_line),
                },
                details=[
                    {
                        "type": "shortage",
                        "path": f"commit_lines[item_id={int(item_id)}]",
                        "item_id": int(item_id),
                        "batch_code": bc_norm,
                        "required_qty": required,
                        "available_qty": int(available),
                        "short_qty": int(short_qty),
                        "reason": str(e),
                    }
                ],
                next_actions=[
                    {"action": "adjust_to_available", "label": "将数量调整为可用量"},
                    {"action": "continue_pick", "label": "继续拣货"},
                    {"action": "go_exception_flow", "label": "转异常流程"},
                ],
            )
        except Exception as e:
            raise e

        return {
            "picked": int(qty),
            "stock_after": result.get("after") if result else None,
            "batch_code": bc_norm,
            "warehouse_id": int(warehouse_id),
            "ref": ref,
            "ref_line": ref_line,
            "status": "OK" if result and result.get("applied", True) else "IDEMPOTENT",
        }
