from __future__ import annotations
from typing import Optional, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

# 优先尝试注入真实库存服务；单测/无依赖时自动回退到占位服务
try:
    from app.services.stock_service import StockService as _RealStockService  # type: ignore
except Exception:  # pragma: no cover
    _RealStockService = None  # type: ignore


class _DefaultStockService:
    async def adjust(self, **kwargs):  # pragma: no cover
        raise NotImplementedError("inject a real StockService or a test double")


class PickService:
    def __init__(self, stock_service: Optional[object] = None):
        if stock_service is not None:
            self.stock = stock_service
        elif _RealStockService is not None:
            self.stock = _RealStockService()
        else:
            self.stock = _DefaultStockService()

    async def _get_task_line_by_context(
        self,
        session: AsyncSession,
        task_id: int,
        item_id: int,
        location_id: Optional[int],
        device_id: Optional[str],
    ) -> int:
        """
        基于 {task_id, item_id, (optional) location_id} 选择唯一行，并做并发护栏：
        - 锁头/行；若任务已分配 assigned_to 且 device_id 不匹配 → 拒绝
        - 仅允许未完成的行（OPEN/PARTIAL）
        """
        row = (
            await session.execute(
                text(
                    """
                SELECT pt.assigned_to, ptl.id
                  FROM pick_task_lines ptl
                  JOIN pick_tasks pt ON pt.id = ptl.task_id
                 WHERE ptl.task_id = :tid
                   AND ptl.item_id = :itm
                   AND ptl.status IN ('OPEN','PARTIAL')
                 FOR UPDATE
                """
                ),
                {"tid": task_id, "itm": item_id},
            )
        ).first()
        if not row:
            raise ValueError("no OPEN/PARTIAL line for the given task_id & item_id")
        assigned_to, line_id = row

        if assigned_to and device_id and assigned_to != device_id:
            raise PermissionError(f"task assigned to {assigned_to}, device {device_id} denied")

        # 可加拣货位策略：校验 location_id 是否在允许集合；当前先放宽
        return int(line_id)

    async def record_pick_by_context(
        self,
        session: AsyncSession,
        task_id: int,
        item_id: int,
        qty: int,
        scan_ref: str,
        *,
        location_id: Optional[int] = None,
        device_id: Optional[str] = None,
        operator: Optional[str] = None,
    ) -> Dict[str, Any]:
        line_id = await self._get_task_line_by_context(session, task_id, item_id, location_id, device_id)
        return await self.record_pick(
            session=session,
            task_line_id=line_id,
            from_location_id=location_id or 0,
            item_id=item_id,
            qty=qty,
            scan_ref=scan_ref,
            device_id=device_id,
            operator=operator,
        )

    async def record_pick(
        self,
        session: AsyncSession,
        task_line_id: int,
        from_location_id: int,
        item_id: int,
        qty: int,
        scan_ref: str,
        *,
        device_id: Optional[str] = None,
        operator: Optional[str] = None,
    ) -> Dict[str, Any]:
        # 1) 锁定任务行 + 并发护栏（assigned_to）
        row = (
            await session.execute(
                text(
                    """
                    SELECT ptl.task_id, ptl.item_id, ptl.req_qty, ptl.picked_qty, pt.assigned_to
                      FROM pick_task_lines ptl
                      JOIN pick_tasks pt ON pt.id = ptl.task_id
                     WHERE ptl.id = :id
                     FOR UPDATE
                """
                ),
                {"id": task_line_id},
            )
        ).first()
        if not row:
            raise ValueError("task line not found")
        task_id, task_item_id, req_qty, picked_qty, assigned_to = row
        if task_item_id != item_id:
            raise ValueError("item mismatch with task line")
        if assigned_to and device_id and assigned_to != device_id:
            raise PermissionError(f"task assigned to {assigned_to}, device {device_id} denied")

        remain = int(req_qty) - int(picked_qty)
        if qty <= 0 or qty > remain:
            raise ValueError(f"invalid qty: {qty}, remain={remain}")

        # 2) 真出库（统一走库存服务；仅传最小必需形参，兼容你当前实现）
        await self.stock.adjust(
            session=session,
            item_id=item_id,
            location_id=from_location_id,
            delta=-qty,
            reason="PICK",
            ref=scan_ref,
        )

        # 3) 累加 picked_qty（触发行/头状态触发器）
        await session.execute(
            text("UPDATE pick_task_lines SET picked_qty = picked_qty + :q, updated_at=now() WHERE id=:id"),
            {"q": qty, "id": task_line_id},
        )

        return {
            "task_id": int(task_id),
            "task_line_id": int(task_line_id),
            "item_id": int(item_id),
            "from_location_id": int(from_location_id),
            "picked": int(qty),
            "remain": int(remain - qty),
        }
