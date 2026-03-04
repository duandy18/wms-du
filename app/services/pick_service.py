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
    v2 拣货（出库）Facade（location_id 已移除；执行域不允许 FEFO / 自动挑批次）：

    设计要点
    - 拣货即扣减：扫码确认后立刻扣减库存（原子 + 幂等由 StockService.adjust_lot 保障）
    - 批次强裁决：以 items.expiry_policy 为唯一真相源
        - REQUIRED：必须显式 batch_code（精确扣某个 SUPPLIER lot）
        - NONE：禁止 batch_code（统一扣 INTERNAL lot）
    - 粒度统一：库存槽位以 (item_id, warehouse_id, lot_id) 表达（Phase M-2 终态）
    - 分析域可提供“临期优先建议”（expiry analytics），但不参与执行扣减

    Phase M-2（结构封板）：
    - 禁止 fallback 到 batch-world（不允许双真相）
    - lot_id 必须存在：无批次商品也必须落到 INTERNAL lot（或等价的具体 lot）
    """

    def __init__(self, stock_svc: Optional[StockService] = None) -> None:
        self.stock_svc = stock_svc or StockService()

    async def _item_requires_batch(self, session: AsyncSession, *, item_id: int) -> bool:
        row = (
            await session.execute(
                SA(
                    """
                    SELECT expiry_policy
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
        return str(row[0] or "").upper() == "REQUIRED"

    async def _resolve_lot_id_by_lot_code(
        self,
        session: AsyncSession,
        *,
        warehouse_id: int,
        item_id: int,
        lot_code: str,
    ) -> Optional[int]:
        code = (lot_code or "").strip()
        if not code:
            return None

        row = (
            await session.execute(
                SA(
                    """
                    SELECT id
                      FROM lots
                     WHERE warehouse_id = :w
                       AND item_id      = :i
                       AND lot_code     = :c
                     LIMIT 1
                    """
                ),
                {"w": int(warehouse_id), "i": int(item_id), "c": str(code)},
            )
        ).first()
        if not row:
            return None
        try:
            return int(row[0])
        except Exception:
            return None

    async def _load_stock_qty(
        self,
        session: AsyncSession,
        *,
        warehouse_id: int,
        item_id: int,
        batch_code: Optional[str],
    ) -> int:
        if batch_code is None:
            row = (
                await session.execute(
                    SA(
                        """
                        SELECT COALESCE(SUM(s.qty), 0) AS qty
                          FROM stocks_lot s
                         WHERE s.warehouse_id = :wid
                           AND s.item_id      = :item_id
                        """
                    ),
                    {"wid": int(warehouse_id), "item_id": int(item_id)},
                )
            ).first()
        else:
            row = (
                await session.execute(
                    SA(
                        """
                        SELECT COALESCE(SUM(s.qty), 0) AS qty
                          FROM stocks_lot s
                          LEFT JOIN lots lo ON lo.id = s.lot_id
                         WHERE s.warehouse_id = :wid
                           AND s.item_id      = :item_id
                           AND lo.lot_code = CAST(:bc AS TEXT)
                        """
                    ),
                    {"wid": int(warehouse_id), "item_id": int(item_id), "bc": str(batch_code)},
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

        if batch_code is None:
            bc_norm: Optional[str] = None
        else:
            s = str(batch_code).strip()
            bc_norm = s or None

        # 终态合同：
        # - REQUIRED：必须 batch_code（精确扣某个 SUPPLIER lot）
        # - NONE：禁止 batch_code（扣 INTERNAL 槽位；系统不再自动 FEFO/自动挑 SUPPLIER lot）
        if requires_batch and not bc_norm:
            raise ValueError("批次受控商品扫码拣货必须提供 batch_code。")
        if (not requires_batch) and bc_norm:
            raise ValueError("非批次商品禁止提供 batch_code。")

        _ = task_line_id
        ref_line = int(start_ref_line or 1)

        try:
            if requires_batch:
                lot_id = await self._resolve_lot_id_by_lot_code(
                    session,
                    warehouse_id=int(warehouse_id),
                    item_id=int(item_id),
                    lot_code=str(bc_norm),
                )
                if lot_id is None:
                    raise ValueError("lot_not_found_for_batch_code")

                result = await self.stock_svc.adjust_lot(
                    session=session,
                    item_id=int(item_id),
                    warehouse_id=int(warehouse_id),
                    lot_id=int(lot_id),
                    delta=-int(qty),
                    reason=movement_type,
                    ref=str(ref),
                    ref_line=int(ref_line),
                    occurred_at=occurred_at,
                    trace_id=trace_id,
                    batch_code=bc_norm,
                    meta={"sub_reason": "PICK"},
                )
            else:
                # NONE：交给 StockService.adjust 走 INTERNAL lot 槽位
                result = await self.stock_svc.adjust(
                    session=session,
                    item_id=int(item_id),
                    warehouse_id=int(warehouse_id),
                    delta=-int(qty),
                    reason=movement_type,
                    ref=str(ref),
                    ref_line=int(ref_line),
                    occurred_at=occurred_at,
                    trace_id=trace_id,
                    batch_code=None,
                    lot_id=None,
                    meta={"sub_reason": "PICK"},
                )

        except ValueError as e:
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
