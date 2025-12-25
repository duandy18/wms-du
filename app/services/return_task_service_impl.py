# app/services/return_task_service_impl.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.enums import MovementType
from app.models.purchase_order import PurchaseOrder
from app.models.purchase_order_line import PurchaseOrderLine
from app.models.return_task import ReturnTask, ReturnTaskLine
from app.services.stock_service import StockService

UTC = timezone.utc


class ReturnTaskServiceImpl:
    """
    采购退货任务服务（实现层）：

    - create_for_po: 从采购单创建退货任务（expected 来自已收数量）；
    - get_with_lines: 获取任务（头 + 行）；
    - record_pick: 在任务上累积拣货数量（只改 picked_qty，不动库存）；
    - commit: 根据 picked_qty 写入 ledger + stocks（delta<0），并更新采购单收货进度。

    核心约束：
    - 退货出库必须知道是哪个批次：record_pick 必须带 batch_code；
    - 真正出库动作只有 commit() → StockService.adjust(delta<0, reason=RETURN_OUT)。
    """

    def __init__(self, stock_svc: Optional[StockService] = None) -> None:
        self.stock_svc = stock_svc or StockService()

    # ------------ 工具：加载采购单 + 行 ------------ #

    async def _load_po(self, session: AsyncSession, po_id: int) -> PurchaseOrder:
        stmt = (
            select(PurchaseOrder)
            .options(selectinload(PurchaseOrder.lines))
            .where(PurchaseOrder.id == po_id)
        )
        res = await session.execute(stmt)
        po = res.scalars().first()
        if po is None:
            raise ValueError(f"PurchaseOrder not found: id={po_id}")
        if po.lines:
            po.lines.sort(key=lambda line: (line.line_no, line.id))
        return po

    # ------------ 创建退货任务 ------------ #

    async def create_for_po(
        self,
        session: AsyncSession,
        *,
        po_id: int,
        warehouse_id: Optional[int] = None,
        include_zero_received: bool = False,
    ) -> ReturnTask:
        po = await self._load_po(session, po_id)
        wh_id = warehouse_id or po.warehouse_id

        task = ReturnTask(
            po_id=po.id,
            supplier_id=po.supplier_id,
            supplier_name=po.supplier_name or po.supplier,
            warehouse_id=wh_id,
            status="DRAFT",
            remark=f"return from PO-{po.id}",
        )
        session.add(task)
        await session.flush()

        lines_to_create: list[ReturnTaskLine] = []
        for line in po.lines or []:
            received = int(line.qty_received or 0)
            if received <= 0 and not include_zero_received:
                continue

            rtl = ReturnTaskLine(
                task_id=task.id,
                po_line_id=line.id,
                item_id=line.item_id,
                item_name=line.item_name,
                batch_code=None,
                expected_qty=received if received > 0 else 0,
                picked_qty=0,
                committed_qty=None,
                status="DRAFT",
            )
            lines_to_create.append(rtl)

        if not lines_to_create:
            raise ValueError(f"采购单 {po.id} 当前没有已收数量可退货，无法创建退货任务")

        for rtl in lines_to_create:
            session.add(rtl)

        await session.flush()
        return await self.get_with_lines(session, task.id)

    # ------------ 查询任务 ------------ #

    async def get_with_lines(
        self,
        session: AsyncSession,
        task_id: int,
        *,
        for_update: bool = False,
    ) -> ReturnTask:
        stmt = (
            select(ReturnTask)
            .options(selectinload(ReturnTask.lines))
            .where(ReturnTask.id == task_id)
        )
        if for_update:
            stmt = stmt.with_for_update()

        res = await session.execute(stmt)
        task = res.scalars().first()
        if task is None:
            raise ValueError(f"ReturnTask not found: id={task_id}")

        if task.lines:
            task.lines.sort(key=lambda line: (line.id,))
        return task

    # ------------ 在任务上累积拣货 ------------ #

    async def record_pick(
        self,
        session: AsyncSession,
        *,
        task_id: int,
        item_id: int,
        qty: int,
        batch_code: Optional[str] = None,
    ) -> ReturnTask:
        if qty == 0:
            return await self.get_with_lines(session, task_id)

        if not batch_code or not str(batch_code).strip():
            raise ValueError("退货拣货必须指定批次 batch_code")

        task = await self.get_with_lines(session, task_id, for_update=True)
        if task.status != "DRAFT":
            raise ValueError(f"任务 {task.id} 状态为 {task.status}，不能再修改")

        norm_code = str(batch_code).strip()

        target: Optional[ReturnTaskLine] = None
        for line in task.lines or []:
            if int(line.item_id) == int(item_id) and (line.batch_code or "") == norm_code:
                target = line
                break

        if target is None:
            target = ReturnTaskLine(
                task_id=task.id,
                po_line_id=None,
                item_id=item_id,
                item_name=None,
                batch_code=norm_code,
                expected_qty=None,
                picked_qty=0,
                committed_qty=None,
                status="DRAFT",
            )
            session.add(target)
            await session.flush()
        else:
            if not target.batch_code:
                target.batch_code = norm_code

        target.picked_qty = int(target.picked_qty or 0) + int(qty)

        if target.expected_qty is not None:
            target.status = (
                "MATCHED"
                if int(target.picked_qty or 0) == int(target.expected_qty or 0)
                else "MISMATCH"
            )
        else:
            target.status = "DRAFT"

        await session.flush()
        return await self.get_with_lines(session, task.id)

    # ------------ commit：真正写 ledger + stocks ------------ #

    async def commit(
        self,
        session: AsyncSession,
        *,
        task_id: int,
        trace_id: Optional[str] = None,
        occurred_at: Optional[datetime] = None,
    ) -> ReturnTask:
        task = await self.get_with_lines(session, task_id, for_update=True)
        if task.status != "DRAFT":
            raise ValueError(f"任务 {task.id} 状态为 {task.status}，不能重复 commit")

        if not task.lines:
            raise ValueError(f"任务 {task.id} 没有任何行，不能 commit")

        now = occurred_at or datetime.now(UTC)
        ref = f"RTN-{task.id}"

        for line in task.lines:
            if int(line.picked_qty or 0) != 0 and not line.batch_code:
                raise ValueError(f"退货 commit 失败：行 item_id={line.item_id} 缺失 batch_code")

        po_lines_map: dict[int, PurchaseOrderLine] = {}
        if task.po_id is not None:
            po = await self._load_po(session, task.po_id)
            for line in po.lines or []:
                po_lines_map[int(line.id)] = line

        ref_line_counter = 0

        for line in task.lines:
            picked = int(line.picked_qty or 0)

            if picked == 0:
                line.committed_qty = 0
                line.status = "COMMITTED"
                continue

            commit_qty = picked
            line.committed_qty = commit_qty
            ref_line_counter += 1

            await self.stock_svc.adjust(
                session=session,
                item_id=int(line.item_id),
                warehouse_id=int(task.warehouse_id),
                delta=-int(commit_qty),
                reason=MovementType.RETURN_OUT,
                ref=ref,
                ref_line=ref_line_counter,
                batch_code=str(line.batch_code or "").strip(),
                occurred_at=now,
                trace_id=trace_id,
            )

            line.status = "COMMITTED"

            if line.po_line_id is not None and int(line.po_line_id) in po_lines_map:
                po_line = po_lines_map[int(line.po_line_id)]
                po_line.qty_received = int(po_line.qty_received or 0) - int(commit_qty)
                if po_line.qty_received < 0:
                    po_line.qty_received = 0

        task.status = "COMMITTED"
        await session.flush()
        return await self.get_with_lines(session, task.id)
