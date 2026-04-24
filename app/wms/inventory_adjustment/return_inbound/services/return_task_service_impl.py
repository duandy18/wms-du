# app/wms/outbound/services/return_task_service_impl.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, Set

from sqlalchemy import Select, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.enums import MovementType
from app.wms.inventory_adjustment.return_inbound.models.return_task import ReturnTask, ReturnTaskLine
from app.wms.ledger.models.stock_ledger import StockLedger
from app.wms.reconciliation.services.three_books_enforcer import enforce_three_books
from app.wms.stock.services.stock_service import StockService

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


def _norm_lot_code(v: str | None) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    return s


async def _load_supplier_lot_snapshot_by_lot_code(
    session: AsyncSession,
    *,
    warehouse_id: int,
    item_id: int,
    lot_code: str | None,
) -> Optional[dict[str, Any]]:
    if lot_code is None:
        return None

    code = _norm_lot_code(lot_code)
    if not code:
        return None

    rows = (
        await session.execute(
            text(
                """
                SELECT id, production_date, expiry_date
                  FROM lots
                 WHERE warehouse_id = :w
                   AND item_id      = :i
                   AND lot_code_source = 'SUPPLIER'
                   AND lot_code = :code
                 LIMIT 2
                """
            ),
            {"w": int(warehouse_id), "i": int(item_id), "code": str(code)},
        )
    ).mappings().all()

    if not rows:
        return None
    if len(rows) > 1:
        return None

    row = rows[0]
    return {
        "id": int(row["id"]),
        "production_date": row.get("production_date"),
        "expiry_date": row.get("expiry_date"),
    }


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
        res = await session.execute(
            select(
                StockLedger.item_id,
                StockLedger.warehouse_id,
                StockLedger.lot_id,
                StockLedger.delta,
                StockLedger.reason,
            )
            .where(StockLedger.ref == str(order_ref))
            .where(StockLedger.delta < 0)
        )

        agg: dict[tuple[int, int, int], int] = {}

        for item_id, wh_id, lot_id, delta, reason in res.all():
            r = str(reason or "").strip().upper()
            if r not in self.SHIP_OUT_REASONS:
                continue
            key = (int(item_id), int(wh_id), int(lot_id))
            agg[key] = agg.get(key, 0) + int(-int(delta or 0))

        lot_ids = sorted({k[2] for k in agg.keys()})
        lot_code_map: dict[int, str | None] = {}
        if lot_ids:
            r2 = await session.execute(
                text("SELECT id, lot_code FROM lots WHERE id = ANY(:ids)"),
                {"ids": lot_ids},
            )
            for x in r2.mappings().all():
                lot_code_map[int(x["id"])] = x.get("lot_code")

        out: list[dict[str, Any]] = []
        for (item_id, wh_id, lot_id), shipped_qty in agg.items():
            if shipped_qty <= 0:
                continue
            out.append(
                {
                    "item_id": item_id,
                    "warehouse_id": wh_id,
                    "lot_id": lot_id,
                    "batch_code": lot_code_map.get(lot_id),
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
            bc = _norm_bc(ln.batch_code)

            resolved_lot_id: Optional[int] = None

            if bc is not None:
                lot_snapshot = await _load_supplier_lot_snapshot_by_lot_code(
                    session,
                    warehouse_id=int(task.warehouse_id),
                    item_id=int(ln.item_id),
                    lot_code=str(bc),
                )
                if lot_snapshot is None:
                    raise ValueError("lot_not_found_for_batch_code")

                resolved_lot_id = int(lot_snapshot["id"])

                # 已经解析到真实 lot_id 后，直接走 lot-only 原语入口，
                # 不再让 RETURN 正增量再次走 batch_code -> 日期裁决。
                res = await self.stock_svc.adjust_lot(
                    session=session,
                    item_id=int(ln.item_id),
                    warehouse_id=int(task.warehouse_id),
                    lot_id=int(resolved_lot_id),
                    delta=+picked,
                    reason=MovementType.RETURN,
                    ref=str(task.order_id),
                    ref_line=ref_line,
                    occurred_at=ts,
                    batch_code=None,
                    production_date=lot_snapshot.get("production_date"),
                    expiry_date=lot_snapshot.get("expiry_date"),
                    trace_id=trace_id,
                    meta={"sub_reason": "RETURN_RECEIPT"},
                )
            else:
                res = await self.stock_svc.adjust(
                    session=session,
                    item_id=int(ln.item_id),
                    delta=+picked,
                    reason=MovementType.RETURN,
                    ref=str(task.order_id),
                    ref_line=ref_line,
                    occurred_at=ts,
                    batch_code=None,
                    warehouse_id=int(task.warehouse_id),
                    trace_id=trace_id,
                    meta={"sub_reason": "RETURN_RECEIPT"},
                )

            applied_lot_id = int(res.get("lot_id") or (resolved_lot_id or 0) or 0)

            effects.append(
                {
                    "warehouse_id": int(task.warehouse_id),
                    "item_id": int(ln.item_id),
                    "lot_id": int(applied_lot_id),
                    "batch_code": bc,
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
