# app/services/return_task_service_impl.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, Set

from sqlalchemy import Select, select, text
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


async def _resolve_lot_id_by_lot_code(
    session: AsyncSession,
    *,
    warehouse_id: int,
    item_id: int,
    lot_code: str | None,
) -> Optional[int]:
    if lot_code is None:
        return None
    row = (
        await session.execute(
            text(
                """
                SELECT id
                  FROM lots
                 WHERE warehouse_id = :w
                   AND item_id      = :i
                   AND lot_code     = :c
                 LIMIT 2
                """
            ),
            {"w": int(warehouse_id), "i": int(item_id), "c": str(lot_code)},
        )
    ).fetchall()
    if not row:
        return None
    if len(row) > 1:
        return None
    return int(row[0][0])


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
        # ✅ lot-only：以 lot_id 聚合 shipped 事实；展示码来自 lots.lot_code
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

        # 批量补齐展示码
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
                batch_code=batch_code,  # ✅ 展示/兼容字段（lots.lot_code）
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

    async def _ensure_return_receipt_id(
        self,
        session: AsyncSession,
        *,
        warehouse_id: int,
        task_id: int,
        order_ref: str,
        trace_id: Optional[str],
        occurred_at: datetime,
    ) -> int:
        """
        Return commit 的终态做法：
        - 用一张 CONFIRMED inbound_receipts 作为“回仓入库事实单据”（source_type='ORDER'）
        - 其 id 用于 INTERNAL lot 的 source_receipt_id（满足 lots 的 DB check）
        """
        # ref 全局唯一：用 task_id + order_ref 组成稳定 ref（同 task 重跑也可命中）
        ref = f"RET-TASK:{int(task_id)}:{str(order_ref)}"
        row = (
            await session.execute(
                text(
                    """
                    SELECT id
                      FROM inbound_receipts
                     WHERE ref = :ref
                     LIMIT 1
                    """
                ),
                {"ref": ref},
            )
        ).first()
        if row is not None:
            return int(row[0])

        r2 = await session.execute(
            text(
                """
                INSERT INTO inbound_receipts(
                  warehouse_id,
                  supplier_id,
                  supplier_name,
                  source_type,
                  source_id,
                  ref,
                  trace_id,
                  status,
                  remark,
                  occurred_at,
                  created_at,
                  updated_at
                )
                VALUES(
                  :w,
                  NULL,
                  NULL,
                  'ORDER',
                  NULL,
                  :ref,
                  :trace_id,
                  'CONFIRMED',
                  'RETURN_TASK_COMMIT',
                  :occurred_at,
                  now(),
                  now()
                )
                RETURNING id
                """
            ),
            {
                "w": int(warehouse_id),
                "ref": ref,
                "trace_id": (str(trace_id) if trace_id else None),
                "occurred_at": occurred_at,
            },
        )
        return int(r2.scalar_one())

    async def _ensure_internal_lot_for_return_line(
        self,
        session: AsyncSession,
        *,
        warehouse_id: int,
        item_id: int,
        receipt_id: int,
        source_line_no: int,
    ) -> int:
        """
        INTERNAL lot 终态：
        - lot_code_source='INTERNAL'
        - lot_code=NULL
        - source_receipt_id/source_line_no NOT NULL（DB check）
        """
        row0 = (
            await session.execute(
                text(
                    """
                    SELECT id
                      FROM lots
                     WHERE warehouse_id = :w
                       AND item_id      = :i
                       AND lot_code_source = 'INTERNAL'
                       AND source_receipt_id = :rid
                       AND source_line_no = :ln
                     LIMIT 1
                    """
                ),
                {"w": int(warehouse_id), "i": int(item_id), "rid": int(receipt_id), "ln": int(source_line_no)},
            )
        ).first()
        if row0 is not None:
            return int(row0[0])

        await session.execute(
            text(
                """
                INSERT INTO lots(
                  warehouse_id,
                  item_id,
                  lot_code_source,
                  lot_code,
                  source_receipt_id,
                  source_line_no,
                  created_at,
                  item_shelf_life_value_snapshot,
                  item_shelf_life_unit_snapshot,
                  item_lot_source_policy_snapshot,
                  item_expiry_policy_snapshot,
                  item_derivation_allowed_snapshot,
                  item_uom_governance_enabled_snapshot
                )
                SELECT
                  :w,
                  it.id,
                  'INTERNAL',
                  NULL,
                  :rid,
                  :ln,
                  now(),
                  it.shelf_life_value,
                  it.shelf_life_unit,
                  it.lot_source_policy,
                  it.expiry_policy,
                  it.derivation_allowed,
                  it.uom_governance_enabled
                FROM items it
                WHERE it.id = :i
                """
            ),
            {"w": int(warehouse_id), "i": int(item_id), "rid": int(receipt_id), "ln": int(source_line_no)},
        )

        row1 = (
            await session.execute(
                text(
                    """
                    SELECT id
                      FROM lots
                     WHERE warehouse_id = :w
                       AND item_id      = :i
                       AND lot_code_source = 'INTERNAL'
                       AND source_receipt_id = :rid
                       AND source_line_no = :ln
                     LIMIT 1
                    """
                ),
                {"w": int(warehouse_id), "i": int(item_id), "rid": int(receipt_id), "ln": int(source_line_no)},
            )
        ).first()
        if row1 is None:
            raise ValueError("failed to ensure INTERNAL lot for return receipt line")
        return int(row1[0])

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

        # ✅ Return commit：必须生成一个 receipt 事实（用于 INTERNAL lot 的 source_receipt_id）
        receipt_id = await self._ensure_return_receipt_id(
            session,
            warehouse_id=int(task.warehouse_id),
            task_id=int(task.id),
            order_ref=str(task.order_id),
            trace_id=trace_id,
            occurred_at=ts,
        )

        lines = list(task.lines or [])
        applied_any = False
        effects: list[dict[str, Any]] = []

        for ln in lines:
            picked = int(ln.picked_qty or 0)
            if picked <= 0:
                continue

            ref_line = int(getattr(ln, "id", 1) or 1)
            bc = _norm_bc(ln.batch_code)

            # ✅ 终态：Return-in 的 RECEIPT 不能复用旧 SUPPLIER lot_id（会撞 uq_ledger_receipt_wh_lot）
            # 为每条 line 建一个 INTERNAL lot（lot_code NULL），以 receipt_id + ref_line 作为来源维度。
            internal_lot_id = await self._ensure_internal_lot_for_return_line(
                session,
                warehouse_id=int(task.warehouse_id),
                item_id=int(ln.item_id),
                receipt_id=int(receipt_id),
                source_line_no=int(ref_line),
            )

            res = await self.stock_svc.adjust(
                session=session,
                item_id=int(ln.item_id),
                delta=+picked,
                reason=MovementType.RETURN,  # canon='RECEIPT'
                ref=str(task.order_id),
                ref_line=ref_line,
                occurred_at=ts,
                batch_code=bc,  # 展示/输入标签（不会落库到 stock_ledger）
                warehouse_id=int(task.warehouse_id),
                trace_id=trace_id,
                lot_id=int(internal_lot_id),
                meta={"sub_reason": "RETURN_RECEIPT"},
            )

            effects.append(
                {
                    "warehouse_id": int(task.warehouse_id),
                    "item_id": int(ln.item_id),
                    "lot_id": int(internal_lot_id),
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
