# app/services/return_task_service_impl.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, Set

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.enums import MovementType
from app.models.return_task import ReturnTask, ReturnTaskLine
from app.models.stock_ledger import StockLedger
from app.services.stock_service import StockService

UTC = timezone.utc


class ReturnTaskServiceImpl:
    """
    订单退货回仓任务服务（实现层）

    核心设计原则：
    ----------------
    1) 退货回仓必须基于“真实出库事实（ledger）”
    2) 批次自动回原批次，不允许人工输入
    3) 所有数量约束由 expected_qty 控制，防止超退

    出库事实判定规则（当前版本）：
    --------------------------------
    - stock_ledger.delta < 0
    - 且 reason ∈ SHIP_OUT_REASONS

    ⚠️ 说明：
    后续若系统统一出库 reason（例如全部收敛为 OUTBOUND_SHIP），
    只需修改 SHIP_OUT_REASONS，不影响其他逻辑。
    """

    # ==============================
    # 出库事实识别（统一入口）
    # ==============================
    SHIP_OUT_REASONS: Set[str] = {
        "SHIPMENT",        # 当前系统存在
        "OUTBOUND_SHIP",   # 标准出库
    }

    def __init__(self, stock_svc: Optional[StockService] = None) -> None:
        self.stock_svc = stock_svc or StockService()

    async def _load_shipped_summary(self, session: AsyncSession, order_ref: str) -> list[dict[str, Any]]:
        """
        从 stock_ledger 反查订单的出库事实（自动回原批次）：

        判定条件：
        - ref == order_ref
        - delta < 0
        - reason ∈ SHIP_OUT_REASONS
        """
        res = await session.execute(
            select(
                StockLedger.item_id,
                StockLedger.warehouse_id,
                StockLedger.batch_code,
                StockLedger.delta,
                StockLedger.reason,
            )
            .where(StockLedger.ref == str(order_ref))
            .where(StockLedger.delta < 0)
        )

        agg: dict[tuple[int, int, str], int] = {}

        for item_id, wh_id, batch_code, delta, reason in res.all():
            r = str(reason or "").strip().upper()
            if r not in self.SHIP_OUT_REASONS:
                continue

            key = (int(item_id), int(wh_id), str(batch_code))
            agg[key] = agg.get(key, 0) + int(-int(delta or 0))  # 转为正数出库量

        out: list[dict[str, Any]] = []
        for (item_id, wh_id, batch_code), shipped_qty in agg.items():
            if shipped_qty <= 0:
                continue
            out.append(
                {
                    "item_id": item_id,
                    "warehouse_id": wh_id,
                    "batch_code": batch_code,
                    "shipped_qty": shipped_qty,
                }
            )
        return out

    # -----------------------------
    # Public methods
    # -----------------------------

    async def create_for_order(
        self,
        session: AsyncSession,
        *,
        order_id: str,  # order_ref
        warehouse_id: Optional[int] = None,
        include_zero_shipped: bool = False,
    ) -> ReturnTask:
        """
        从订单出库事实（ledger）创建退货回仓任务。

        - 唯一入口：order_id（即 order_ref 字符串）
        - 批次：来自 ledger.batch_code（自动回原批次）
        - expected_qty：来自出库事实 shipped_qty
        - picked_qty：初始为 0（等待 record_receive）
        """
        order_ref = str(order_id).strip()
        if not order_ref:
            raise ValueError("order_id(order_ref) is required")

        # 幂等：若已有未提交任务，直接返回（避免重复创建导致用户困惑）
        existing_stmt: Select = (
            select(ReturnTask)
            .where(ReturnTask.order_id == order_ref)
            .where(ReturnTask.status != "COMMITTED")
            .order_by(ReturnTask.id.desc())
            .options(selectinload(ReturnTask.lines))
            .limit(1)
        )
        existing = (await session.execute(existing_stmt)).scalars().first()
        if existing is not None:
            return existing

        shipped = await self._load_shipped_summary(session, order_ref)

        if warehouse_id is not None:
            shipped = [x for x in shipped if int(x["warehouse_id"]) == int(warehouse_id)]

        if not include_zero_shipped:
            shipped = [x for x in shipped if int(x.get("shipped_qty") or 0) > 0]

        if not shipped:
            raise ValueError(f"order_ref={order_ref} has no shippable ledger facts for return")

        # 退货回仓任务目前要求“单仓作业”（与前端作业台一致）
        wh_ids = sorted({int(x["warehouse_id"]) for x in shipped})
        if len(wh_ids) != 1:
            raise ValueError(f"order_ref={order_ref} is multi-warehouse: {wh_ids}")
        wh_id = wh_ids[0]

        task = ReturnTask(
            order_id=order_ref,
            warehouse_id=wh_id,
            status="OPEN",
            remark=None,
        )

        session.add(task)
        await session.flush()  # 获取 task.id

        for x in shipped:
            item_id = int(x["item_id"])
            batch_code = str(x["batch_code"])
            expected_qty = int(x["shipped_qty"])

            line = ReturnTaskLine(
                task_id=task.id,
                order_line_id=None,
                item_id=item_id,
                batch_code=batch_code,
                expected_qty=expected_qty,
                picked_qty=0,
                committed_qty=0,
                status="OPEN",
                remark=None,
            )
            session.add(line)

        await session.flush()
        return await self.get_with_lines(session, task_id=int(task.id), for_update=False)

    async def get_with_lines(
        self,
        session: AsyncSession,
        task_id: int,
        *,
        for_update: bool = False,
    ) -> ReturnTask:
        stmt = (
            select(ReturnTask)
            .where(ReturnTask.id == int(task_id))
            .options(selectinload(ReturnTask.lines))
        )
        if for_update:
            stmt = stmt.with_for_update()

        task = (await session.execute(stmt)).scalars().first()
        if task is None:
            raise ValueError(f"return_task not found: id={task_id}")
        return task

    async def record_receive(
        self,
        session: AsyncSession,
        *,
        task_id: int,
        item_id: int,
        qty: int,
    ) -> ReturnTask:
        """
        记录一次数量（增量）：

        - qty 可正可负（撤销误录）
        - 强约束：最终 picked_qty ∈ [0, expected_qty]
        """
        task = await self.get_with_lines(session, task_id=task_id, for_update=True)
        if task.status == "COMMITTED":
            return task

        lines = list(task.lines or [])
        target = None
        for ln in lines:
            if int(ln.item_id) == int(item_id):
                target = ln
                break
        if target is None:
            raise ValueError(f"task_line not found for item_id={item_id}")

        expected = int(target.expected_qty or 0)
        current = int(target.picked_qty or 0)
        next_qty = current + int(qty)

        if next_qty < 0:
            raise ValueError("picked_qty cannot be < 0")
        if next_qty > expected:
            raise ValueError(f"picked_qty({next_qty}) > expected_qty({expected})")

        target.picked_qty = next_qty
        await session.flush()

        return await self.get_with_lines(session, task_id=task_id, for_update=False)

    async def commit(
        self,
        session: AsyncSession,
        *,
        task_id: int,
        trace_id: Optional[str] = None,
        occurred_at: Optional[datetime] = None,
    ) -> ReturnTask:
        """
        提交回仓：把 picked_qty 入库到原批次（RECEIPT 口径）。

        - 幂等：若任务已 COMMITTED，直接返回
        - 逐行入库：delta = picked_qty（正数）
        - 批次：line.batch_code（自动回原批次）
        """
        task = await self.get_with_lines(session, task_id=task_id, for_update=True)
        if task.status == "COMMITTED":
            return task

        ts = occurred_at or datetime.now(UTC)

        lines = list(task.lines or [])
        applied_any = False

        for ln in lines:
            picked = int(ln.picked_qty or 0)
            if picked <= 0:
                continue

            await self.stock_svc.adjust(
                session=session,
                item_id=int(ln.item_id),
                delta=+picked,
                reason=MovementType.RETURN,  # 映射为 RECEIPT（回仓入库）
                ref=str(task.order_id),
                ref_line=int(getattr(ln, "id", 1) or 1),
                occurred_at=ts,
                batch_code=str(ln.batch_code),
                warehouse_id=int(task.warehouse_id),
                trace_id=trace_id,
            )

            ln.committed_qty = picked
            ln.status = "COMMITTED"
            applied_any = True

        task.status = "COMMITTED"
        if applied_any:
            task.updated_at = ts  # 若模型没有该字段也不会影响（SQLAlchemy 会忽略不存在属性）

        await session.flush()
        return await self.get_with_lines(session, task_id=task_id, for_update=False)
