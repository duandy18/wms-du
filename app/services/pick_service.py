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
    - 拣货即扣减：扫码确认后立刻扣减库存（原子 + 幂等由 StockService.adjust_lot 保障）
    - 批次强制：仅对 requires_batch=true 的商品强制 batch_code；requires_batch=false 允许 NULL
    - 粒度统一：库存槽位以 (item_id, warehouse_id, lot_id) 表达（Phase M-2 终态）
    - FEFO 柔性：不强制 FEFO，只要指定批次即可扣减；未指定批次时按 FEFO/lot_id 选槽

    Phase M-2（结构封板）：
    - 禁止 fallback 到 batch-world（不允许双真相）
    - lot_id 必须存在：无批次商品也必须落到 INTERNAL lot（或等价的具体 lot）
    """

    def __init__(self, stock_svc: Optional[StockService] = None) -> None:
        self.stock_svc = stock_svc or StockService()

    async def _item_requires_batch(self, session: AsyncSession, *, item_id: int) -> bool:
        """
        批次受控唯一真相源：items.expiry_policy
        - expiry_policy='REQUIRED' => requires_batch=True
        - 其他（False/NULL/NONE）  => requires_batch=False
        """
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
        """
        将扫码得到的 batch_code 视为展示码 lot_code，解析到 lots.id。
        找不到则返回 None（上层决定是否允许）。
        """
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

    async def _pick_fefo_lot_id_for_item(
        self,
        session: AsyncSession,
        *,
        warehouse_id: int,
        item_id: int,
    ) -> Optional[int]:
        """
        当 requires_batch=false 且未提供 batch_code 时，必须选择一个真实 lot 槽位扣减。
        这里采用 FEFO-ish 策略：expiry_date ASC NULLS LAST, lot_id ASC。
        """
        row = (
            await session.execute(
                SA(
                    """
                    SELECT s.lot_id
                      FROM stocks_lot s
                      LEFT JOIN lots lo ON lo.id = s.lot_id
                     WHERE s.warehouse_id = :w
                       AND s.item_id      = :i
                       AND s.qty > 0
                     ORDER BY lo.expiry_date ASC NULLS LAST, s.lot_id ASC
                     LIMIT 1
                    """
                ),
                {"w": int(warehouse_id), "i": int(item_id)},
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
        """
        用于“库存不足”时给出缺口明细（只读，不参与扣减裁决）：
        - 只读 stocks_lot（lot-world）
        - batch_code 作为 lot_code 匹配 lots.lot_code
        """
        row = (
            await session.execute(
                SA(
                    """
                    SELECT COALESCE(SUM(s.qty), 0) AS qty
                      FROM stocks_lot s
                      LEFT JOIN lots lo ON lo.id = s.lot_id
                     WHERE s.warehouse_id = :wid
                       AND s.item_id      = :item_id
                       AND lo.lot_code IS NOT DISTINCT FROM CAST(:bc AS TEXT)
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

        if batch_code is None:
            bc_norm: Optional[str] = None
        else:
            s = str(batch_code).strip()
            bc_norm = s or None

        if requires_batch and not bc_norm:
            raise ValueError("批次受控商品扫码拣货必须提供 batch_code。")

        _ = task_line_id
        ref_line = int(start_ref_line or 1)

        try:
            # 终态：只走 lot-world
            lot_id: Optional[int] = None

            if bc_norm:
                lot_id = await self._resolve_lot_id_by_lot_code(
                    session,
                    warehouse_id=int(warehouse_id),
                    item_id=int(item_id),
                    lot_code=str(bc_norm),
                )
                if lot_id is None:
                    raise ValueError("lot_not_found_for_batch_code")

            if lot_id is None:
                # requires_batch=false：未提供 batch_code，按 FEFO-ish 选一个可扣减 lot
                lot_id = await self._pick_fefo_lot_id_for_item(
                    session,
                    warehouse_id=int(warehouse_id),
                    item_id=int(item_id),
                )
                if lot_id is None:
                    raise ValueError("insufficient_stock")

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
                batch_code=bc_norm,  # 展示码（可为空）
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
