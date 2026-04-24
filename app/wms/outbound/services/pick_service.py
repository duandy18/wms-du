# app/wms/outbound/services/pick_service.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, Union

from sqlalchemy import text as SA
from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.shared.enums import MovementType
from app.wms.stock.services.stock_service import StockService


def _norm_lot_code(v: str | None) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


class PickService:
    """
    轻量 pick 入口（历史/兼容 API 使用）：

    - record_pick：按 (warehouse,item,batch_code?) 扣减库存并写台账
    - SUPPLIER（batch_code 非空）：必须能解析到既有 lot_id（不允许 outflow 时隐式创建 lot）
    - NONE（batch_code 为空）：由 StockService 走 INTERNAL 单例 lot（合同闸门裁决）

    当前中心任务收口：
    - REQUIRED lot 身份已经切到 production_date
    - batch_code / lot_code 不再是结构身份，只能作为辅助解析输入
    - 若同一个 lot_code 命中多个 SUPPLIER lots，必须显式报歧义
    """

    def __init__(self, stock_svc: Optional[StockService] = None) -> None:
        self.stock_svc = stock_svc or StockService()

    async def _resolve_lot_id_by_lot_code(
        self,
        session: AsyncSession,
        *,
        warehouse_id: int,
        item_id: int,
        lot_code: str,
    ) -> Optional[int]:
        lot_norm = _norm_lot_code(lot_code)
        if lot_norm is None:
            return None

        rows = (
            await session.execute(
                SA(
                    """
                    SELECT id
                      FROM lots
                     WHERE warehouse_id = :w
                       AND item_id      = :i
                       AND lot_code_source = 'SUPPLIER'
                       AND lot_code = :code
                     ORDER BY id ASC
                     LIMIT 2
                    """
                ),
                {"w": int(warehouse_id), "i": int(item_id), "code": str(lot_norm)},
            )
        ).all()

        if not rows:
            return None
        if len(rows) > 1:
            raise ValueError("supplier_lot_code_ambiguous")

        return int(rows[0][0])

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
        start_ref_line: int = 1,
        movement_type: Union[str, MovementType] = MovementType.SHIP,
    ) -> Dict[str, Any]:
        """
        记录一次拣货/出库扣减（旧 pick API 的执行入口）。

        - qty 必须 > 0（本函数内部会写 delta=-qty）
        - batch_code:
            * REQUIRED 商品：非空（由路由/contract 校验保证）
            * NONE 商品：必须为 None（由路由/contract 校验保证）

        当前阶段：
        - SUPPLIER（batch_code 非空）路径走 StockService.adjust_lot
        - NONE（batch_code 为空）路径继续走 StockService.adjust
        """
        if int(qty) <= 0:
            raise ValueError("pick_qty_must_be_positive")

        bc_norm = _norm_lot_code(batch_code)

        # SUPPLIER：必须解析到既有 lot_id，否则拒绝
        if bc_norm is not None:
            resolved_lot_id = await self._resolve_lot_id_by_lot_code(
                session,
                warehouse_id=int(warehouse_id),
                item_id=int(item_id),
                lot_code=str(bc_norm),
            )
            if resolved_lot_id is None:
                raise ValueError("lot_not_found")

            res = await self.stock_svc.adjust_lot(
                session=session,
                item_id=int(item_id),
                warehouse_id=int(warehouse_id),
                lot_id=int(resolved_lot_id),
                delta=-int(qty),
                reason=movement_type,
                ref=str(ref),
                ref_line=int(start_ref_line),
                occurred_at=occurred_at,
                batch_code=bc_norm,
                production_date=None,
                expiry_date=None,
                trace_id=trace_id,
                shadow_write_stocks=False,
            )
        else:
            res = await self.stock_svc.adjust(
                session=session,
                item_id=int(item_id),
                warehouse_id=int(warehouse_id),
                delta=-int(qty),
                reason=movement_type,
                ref=str(ref),
                ref_line=int(start_ref_line),
                occurred_at=occurred_at,
                batch_code=None,
                production_date=None,
                expiry_date=None,
                trace_id=trace_id,
                lot_id=None,
            )

        return {
            "status": "OK",
            "picked": int(qty),
            "warehouse_id": int(warehouse_id),
            "batch_code": bc_norm,
            "ref": str(ref),
            "ref_line": int(start_ref_line),
            "stock_after": res.get("after"),
            "idempotent": bool(res.get("idempotent", False)),
            "applied": bool(res.get("applied", True)),
        }
