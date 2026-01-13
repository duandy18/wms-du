# scripts/backfill_inbound_receipts.py
from __future__ import annotations

import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _env(name: str, default: str | None = None) -> str:
    v = os.getenv(name)
    if v is None or not str(v).strip():
        if default is None:
            raise RuntimeError(f"missing env: {name}")
        return default
    return str(v).strip()


def _infer_ref(source_type: str | None, task_id: int, source_id: int | None) -> str:
    st = (source_type or "").strip().upper()
    if st == "ORDER":
        # 与 receive_task_commit.py 的 ref 规则一致：RMA-{source_id or task_id}
        sid = int(source_id or 0) or int(task_id)
        return f"RMA-{sid}"
    return f"RT-{int(task_id)}"


async def _task_has_receipt(session: AsyncSession, task_id: int) -> bool:
    row = (
        await session.execute(
            text("SELECT 1 FROM inbound_receipts WHERE receive_task_id = :tid LIMIT 1"),
            {"tid": int(task_id)},
        )
    ).first()
    return row is not None


async def _load_tasks(session: AsyncSession, limit: int = 5000) -> List[Dict[str, Any]]:
    # 只回填已 COMMITTED 的任务
    rows = (
        await session.execute(
            text(
                """
                SELECT id, source_type, source_id, po_id, supplier_id, supplier_name,
                       warehouse_id, remark, updated_at
                  FROM receive_tasks
                 WHERE status = 'COMMITTED'
                 ORDER BY id ASC
                 LIMIT :lim
                """
            ),
            {"lim": int(limit)},
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def _load_task_lines(session: AsyncSession, task_id: int) -> List[Dict[str, Any]]:
    rows = (
        await session.execute(
            text(
                """
                SELECT id, task_id, po_line_id, item_id, item_name, item_sku,
                       units_per_case, batch_code, production_date, expiry_date,
                       scanned_qty, committed_qty, remark
                  FROM receive_task_lines
                 WHERE task_id = :tid
                 ORDER BY id ASC
                """
            ),
            {"tid": int(task_id)},
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def _load_po_line(session: AsyncSession, po_line_id: int) -> Optional[Dict[str, Any]]:
    row = (
        await session.execute(
            text(
                """
                SELECT id, item_id, item_name, item_sku, supply_price, line_amount
                  FROM purchase_order_lines
                 WHERE id = :lid
                 LIMIT 1
                """
            ),
            {"lid": int(po_line_id)},
        )
    ).mappings().first()
    return dict(row) if row else None


async def _insert_receipt(
    session: AsyncSession,
    *,
    task: Dict[str, Any],
    ref: str,
    trace_id: Optional[str],
    occurred_at: datetime,
) -> int:
    row = (
        await session.execute(
            text(
                """
                INSERT INTO inbound_receipts(
                    warehouse_id, supplier_id, supplier_name,
                    source_type, source_id, receive_task_id,
                    ref, trace_id, status, remark,
                    occurred_at, created_at, updated_at
                )
                VALUES (
                    :warehouse_id, :supplier_id, :supplier_name,
                    :source_type, :source_id, :receive_task_id,
                    :ref, :trace_id, 'CONFIRMED', :remark,
                    :occurred_at, :occurred_at, :occurred_at
                )
                RETURNING id
                """
            ),
            {
                "warehouse_id": int(task["warehouse_id"]),
                "supplier_id": int(task["supplier_id"]) if task.get("supplier_id") is not None else None,
                "supplier_name": str(task.get("supplier_name") or "") or None,
                "source_type": str(task.get("source_type") or "PO"),
                "source_id": int(task["source_id"]) if task.get("source_id") is not None else None,
                "receive_task_id": int(task["id"]),
                "ref": ref,
                "trace_id": trace_id,
                "remark": str(task.get("remark") or "") or None,
                "occurred_at": occurred_at,
            },
        )
    ).first()
    if not row:
        raise RuntimeError("failed to insert inbound_receipts")
    return int(row[0])


async def _insert_line(
    session: AsyncSession,
    *,
    receipt_id: int,
    line_no: int,
    task_line: Dict[str, Any],
    po_line: Optional[Dict[str, Any]],
    occurred_at: datetime,
) -> None:
    qty_purchase = int(task_line.get("committed_qty") or task_line.get("scanned_qty") or 0)
    if qty_purchase <= 0:
        return

    factor = int(task_line.get("units_per_case") or 1)
    if factor <= 0:
        factor = 1
    qty_units = qty_purchase * factor

    # 快照字段：优先 PO 行快照，否则用任务行快照
    item_name = None
    item_sku = None
    unit_cost: Optional[Decimal] = None
    line_amount: Optional[Decimal] = None
    po_line_id_val: Optional[int] = None

    if po_line is not None:
        po_line_id_val = int(po_line["id"])
        item_name = po_line.get("item_name")
        item_sku = po_line.get("item_sku")
        if po_line.get("supply_price") is not None:
            unit_cost = Decimal(str(po_line["supply_price"]))
        if unit_cost is not None:
            line_amount = (Decimal(int(qty_units)) * unit_cost).quantize(Decimal("0.01"))

    if not item_name:
        item_name = task_line.get("item_name")
    if not item_sku:
        item_sku = task_line.get("item_sku")

    await session.execute(
        text(
            """
            INSERT INTO inbound_receipt_lines(
                receipt_id, line_no,
                po_line_id, item_id,
                item_name, item_sku,
                batch_code, production_date, expiry_date,
                qty_received, units_per_case, qty_units,
                unit_cost, line_amount,
                remark, created_at, updated_at
            )
            VALUES (
                :receipt_id, :line_no,
                :po_line_id, :item_id,
                :item_name, :item_sku,
                :batch_code, :production_date, :expiry_date,
                :qty_received, :units_per_case, :qty_units,
                :unit_cost, :line_amount,
                :remark, :now, :now
            )
            """
        ),
        {
            "receipt_id": int(receipt_id),
            "line_no": int(line_no),
            "po_line_id": po_line_id_val,
            "item_id": int(task_line["item_id"]),
            "item_name": str(item_name) if item_name else None,
            "item_sku": str(item_sku) if item_sku else None,
            "batch_code": str(task_line.get("batch_code") or "NOEXP"),
            "production_date": task_line.get("production_date"),
            "expiry_date": task_line.get("expiry_date"),
            "qty_received": int(qty_purchase),
            "units_per_case": int(factor),
            "qty_units": int(qty_units),
            "unit_cost": unit_cost,
            "line_amount": line_amount,
            "remark": str(task_line.get("remark") or "") or None,
            "now": occurred_at,
        },
    )


async def backfill() -> Tuple[int, int]:
    dsn = _env("WMS_DATABASE_URL")
    # 兼容：有人传的是 sync DSN（postgresql+psycopg://），这里要求 async（postgresql+psycopg:// 也能被 async_engine 接受）
    engine = create_async_engine(dsn, pool_pre_ping=True)
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    created_receipts = 0
    created_lines = 0

    async with async_session() as session:
        tasks = await _load_tasks(session)
        for t in tasks:
            tid = int(t["id"])
            if await _task_has_receipt(session, tid):
                continue

            lines = await _load_task_lines(session, tid)
            # 只处理有实收的任务
            real_lines = [ln for ln in lines if int(ln.get("scanned_qty") or 0) > 0 or int(ln.get("committed_qty") or 0) > 0]
            if not real_lines:
                continue

            occurred_at = t.get("updated_at") or _utc_now()
            if isinstance(occurred_at, str):
                # 极端情况：字符串时间，直接用 now（避免解析失败）
                occurred_at = _utc_now()

            ref = _infer_ref(t.get("source_type"), tid, t.get("source_id"))
            trace_id = None  # 历史任务多半没有 trace_id；如未来有字段可补

            receipt_id = await _insert_receipt(
                session,
                task=t,
                ref=ref,
                trace_id=trace_id,
                occurred_at=occurred_at,
            )
            created_receipts += 1

            line_no = 0
            for ln in real_lines:
                line_no += 1
                po_line = None
                if ln.get("po_line_id") is not None:
                    po_line = await _load_po_line(session, int(ln["po_line_id"]))
                await _insert_line(
                    session,
                    receipt_id=receipt_id,
                    line_no=line_no,
                    task_line=ln,
                    po_line=po_line,
                    occurred_at=occurred_at,
                )
                created_lines += 1

        await session.commit()

    await engine.dispose()
    return created_receipts, created_lines


if __name__ == "__main__":
    import asyncio

    n_receipts, n_lines = asyncio.run(backfill())
    print(f"[backfill] created receipts={n_receipts} lines={n_lines}")
