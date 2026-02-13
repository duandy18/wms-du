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
from app.services.three_books_enforcer import enforce_three_books

UTC = timezone.utc


def _norm_bc(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        if not s or s.lower() == "none":
            return None
        return s
    s2 = str(v).strip()
    if not s2 or s2.lower() == "none":
        return None
    return s2


def _batch_key(bc: Optional[str]) -> str:
    return bc if bc is not None else "__NULL_BATCH__"


class ReturnTaskServiceImpl:
    """
    订单退货回仓任务服务（实现层）
    （其余注释省略，保持原样）
    """

    SHIP_OUT_REASONS: Set[str] = {
        "SHIPMENT",
        "OUTBOUND_SHIP",
    }

    def __init__(self, stock_svc: Optional[StockService] = None) -> None:
        self.stock_svc = stock_svc or StockService()

    async def _load_shipped_summary(self, session: AsyncSession, order_ref: str) -> list[dict[str, Any]]:
        # ✅ 用 batch_code_key 聚合 shipped 事实，避免 NULL/"None" 分裂
        res = await session.execute(
            select(
                StockLedger.item_id,
                StockLedger.warehouse_id,
                StockLedger.batch_code,
                StockLedger.batch_code_key,
                StockLedger.delta,
                StockLedger.reason,
            )
            .where(StockLedger.ref == str(order_ref))
            .where(StockLedger.delta < 0)
        )

        # key: (item, wh, batch_code_key)
        agg: dict[tuple[int, int, str], int] = {}
        any_bc: dict[tuple[int, int, str], Optional[str]] = {}

        for item_id, wh_id, batch_code, batch_code_key, delta, reason in res.all():
            r = str(reason or "").strip().upper()
            if r not in self.SHIP_OUT_REASONS:
                continue

            bc = _norm_bc(batch_code)
            ck = str(batch_code_key or _batch_key(bc))
            key = (int(item_id), int(wh_id), ck)

            agg[key] = agg.get(key, 0) + int(-int(delta or 0))
            any_bc.setdefault(key, bc)

        out: list[dict[str, Any]] = []
        for (item_id, wh_id, ck), shipped_qty in agg.items():
            if shipped_qty <= 0:
                continue
            out.append(
                {
                    "item_id": item_id,
                    "warehouse_id": wh_id,
                    "batch_code": any_bc.get((item_id, wh_id, ck)),
                    "batch_code_key": ck,
                    "shipped_qty": shipped_qty,
                }
            )
        return out

    async def create_for_order(
        self,
        session: AsyncSession,
        *,
        order_id: str,
        warehouse_id: Optional[int] = None,
        include_zero_shipped: bool = False,
    ) -> ReturnTask:
        order_ref = str(order_id).strip()
        if not order_ref:
            raise ValueError("order_id(order_ref) is required")

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
        await session.flush()

        for x in shipped:
            item_id = int(x["item_id"])
            batch_code = _norm_bc(x.get("batch_code"))
            expected_qty = int(x["shipped_qty"])

            line = ReturnTaskLine(
                task_id=task.id,
                order_line_id=None,
                item_id=item_id,
                batch_code=batch_code,  # ✅ may be NULL（非批次商品回仓）
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
        task = await self.get_with_lines(session, task_id=task_id, for_update=True)
        if task.status == "COMMITTED":
            return task

        ts = occurred_at or datetime.now(UTC)

        lines = list(task.lines or [])
        applied_any = False
        effects: list[dict[str, Any]] = []

        for ln in lines:
            picked = int(ln.picked_qty or 0)
            if picked <= 0:
                continue

            ref_line = int(getattr(ln, "id", 1) or 1)

            res = await self.stock_svc.adjust(
                session=session,
                item_id=int(ln.item_id),
                delta=+picked,
                reason=MovementType.RETURN,
                ref=str(task.order_id),
                ref_line=ref_line,
                occurred_at=ts,
                batch_code=_norm_bc(ln.batch_code),  # ✅ keep NULL, forbid "None"
                warehouse_id=int(task.warehouse_id),
                trace_id=trace_id,
                meta={"sub_reason": "RETURN_RECEIPT"},
            )

            effects.append(
                {
                    "warehouse_id": int(task.warehouse_id),
                    "item_id": int(ln.item_id),
                    "batch_code": _norm_bc(ln.batch_code),
                    "qty": int(picked),
                    "ref": str(task.order_id),
                    "ref_line": ref_line,
                    "reason": str(res.get("reason") or ""),
                }
            )

            ln.committed_qty = picked
            ln.status = "COMMITTED"
            applied_any = True

        task.status = "COMMITTED"
        if applied_any:
            task.updated_at = ts

        await session.flush()

        if effects:
            await enforce_three_books(session, ref=str(task.order_id), effects=effects, at=ts)

        return await self.get_with_lines(session, task_id=int(task.id), for_update=False)
