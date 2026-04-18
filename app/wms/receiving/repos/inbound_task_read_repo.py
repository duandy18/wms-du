from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.inbound.repos.item_lookup_repo import get_item_policy_by_id
from app.wms.receiving.contracts.inbound_task_read import (
    InboundTaskLineOut,
    InboundTaskListItemOut,
    InboundTaskListOut,
    InboundTaskReadOut,
)


async def list_inbound_tasks_repo(session: AsyncSession) -> InboundTaskListOut:
    rows = (
        await session.execute(
            text(
                """
                WITH line_received AS (
                  SELECT
                    o.receipt_no_snapshot AS receipt_no,
                    ol.receipt_line_no_snapshot AS line_no,
                    COALESCE(SUM(ol.qty_inbound), 0) AS received_qty
                  FROM wms_inbound_operations o
                  JOIN wms_inbound_operation_lines ol
                    ON ol.wms_inbound_operation_id = o.id
                  GROUP BY
                    o.receipt_no_snapshot,
                    ol.receipt_line_no_snapshot
                )
                SELECT
                  r.id AS receipt_id,
                  r.receipt_no,
                  r.source_type,
                  r.source_doc_no_snapshot,
                  r.warehouse_id,
                  r.warehouse_name_snapshot,
                  r.supplier_id,
                  r.counterparty_name_snapshot,
                  r.status,
                  r.released_at,
                  r.remark,
                  COUNT(l.id) AS line_count,
                  COALESCE(SUM(l.planned_qty), 0) AS total_planned_qty,
                  COALESCE(SUM(COALESCE(lr.received_qty, 0)), 0) AS total_received_qty,
                  COALESCE(
                    SUM(GREATEST(l.planned_qty - COALESCE(lr.received_qty, 0), 0)),
                    0
                  ) AS total_remaining_qty
                FROM inbound_receipts r
                JOIN inbound_receipt_lines l
                  ON l.inbound_receipt_id = r.id
                LEFT JOIN line_received lr
                  ON lr.receipt_no = r.receipt_no
                 AND lr.line_no = l.line_no
                WHERE r.status = 'RELEASED'
                GROUP BY
                  r.id,
                  r.receipt_no,
                  r.source_type,
                  r.source_doc_no_snapshot,
                  r.warehouse_id,
                  r.warehouse_name_snapshot,
                  r.supplier_id,
                  r.counterparty_name_snapshot,
                  r.status,
                  r.released_at,
                  r.remark
                ORDER BY
                  r.released_at DESC NULLS LAST,
                  r.id DESC
                """
            )
        )
    ).mappings().all()

    return InboundTaskListOut(
        items=[
            InboundTaskListItemOut(
                receipt_id=int(r["receipt_id"]),
                receipt_no=str(r["receipt_no"]),
                source_type=str(r["source_type"]),
                source_doc_no_snapshot=r["source_doc_no_snapshot"],
                warehouse_id=int(r["warehouse_id"]),
                warehouse_name_snapshot=r["warehouse_name_snapshot"],
                supplier_id=r["supplier_id"],
                counterparty_name_snapshot=r["counterparty_name_snapshot"],
                status=str(r["status"]),
                released_at=r["released_at"],
                line_count=int(r["line_count"]),
                total_planned_qty=r["total_planned_qty"],
                total_received_qty=r["total_received_qty"],
                total_remaining_qty=r["total_remaining_qty"],
                remark=r["remark"],
            )
            for r in rows
        ],
        total=len(rows),
    )


async def get_inbound_task_repo(
    session: AsyncSession,
    *,
    receipt_no: str,
) -> InboundTaskReadOut:
    header = (
        await session.execute(
            text(
                """
                SELECT
                  id AS receipt_id,
                  receipt_no,
                  source_type,
                  source_doc_no_snapshot,
                  warehouse_id,
                  warehouse_name_snapshot,
                  supplier_id,
                  counterparty_name_snapshot,
                  status,
                  remark
                FROM inbound_receipts
                WHERE receipt_no = :receipt_no
                LIMIT 1
                """
            ),
            {"receipt_no": str(receipt_no)},
        )
    ).mappings().first()

    if header is None:
        raise HTTPException(status_code=404, detail="inbound_task_not_found")

    if str(header["status"]) != "RELEASED":
        raise HTTPException(
            status_code=409,
            detail=f"inbound_task_not_released:{header['status']}",
        )

    rows = (
        await session.execute(
            text(
                """
                SELECT
                  l.line_no,
                  l.item_id,
                  l.item_uom_id,
                  l.planned_qty,
                  l.item_name_snapshot,
                  l.item_spec_snapshot,
                  l.uom_name_snapshot,
                  l.ratio_to_base_snapshot,
                  COALESCE(SUM(ol.qty_inbound), 0) AS received_qty,
                  GREATEST(l.planned_qty - COALESCE(SUM(ol.qty_inbound), 0), 0) AS remaining_qty,
                  l.remark
                FROM inbound_receipt_lines l
                LEFT JOIN wms_inbound_operations o
                  ON o.receipt_no_snapshot = :receipt_no
                LEFT JOIN wms_inbound_operation_lines ol
                  ON ol.wms_inbound_operation_id = o.id
                 AND ol.receipt_line_no_snapshot = l.line_no
                WHERE l.inbound_receipt_id = :receipt_id
                GROUP BY
                  l.line_no,
                  l.item_id,
                  l.item_uom_id,
                  l.planned_qty,
                  l.item_name_snapshot,
                  l.item_spec_snapshot,
                  l.uom_name_snapshot,
                  l.ratio_to_base_snapshot,
                  l.remark
                ORDER BY l.line_no ASC
                """
            ),
            {
                "receipt_no": str(receipt_no),
                "receipt_id": int(header["receipt_id"]),
            },
        )
    ).mappings().all()

    policy_cache: dict[int, object] = {}
    lines: list[InboundTaskLineOut] = []

    for r in rows:
        item_id = int(r["item_id"])
        policy = policy_cache.get(item_id)
        if policy is None:
            policy = await get_item_policy_by_id(
                session,
                item_id=item_id,
            )
            if policy is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"item_policy_not_found:{item_id}",
                )
            policy_cache[item_id] = policy

        shelf_life_value_raw = getattr(policy, "shelf_life_value", None)
        shelf_life_unit_raw = getattr(policy, "shelf_life_unit", None)

        lines.append(
            InboundTaskLineOut(
                line_no=int(r["line_no"]),
                item_id=item_id,
                item_uom_id=int(r["item_uom_id"]),
                planned_qty=r["planned_qty"],
                item_name_snapshot=r["item_name_snapshot"],
                item_spec_snapshot=r["item_spec_snapshot"],
                uom_name_snapshot=r["uom_name_snapshot"],
                ratio_to_base_snapshot=r["ratio_to_base_snapshot"],
                expiry_policy=str(getattr(policy, "expiry_policy")),
                lot_source_policy=str(getattr(policy, "lot_source_policy")),
                derivation_allowed=bool(getattr(policy, "derivation_allowed")),
                shelf_life_value=(
                    int(shelf_life_value_raw)
                    if shelf_life_value_raw is not None
                    else None
                ),
                shelf_life_unit=(
                    str(shelf_life_unit_raw)
                    if shelf_life_unit_raw is not None
                    else None
                ),
                received_qty=r["received_qty"],
                remaining_qty=r["remaining_qty"],
                remark=r["remark"],
            )
        )

    return InboundTaskReadOut(
        receipt_id=int(header["receipt_id"]),
        receipt_no=str(header["receipt_no"]),
        source_type=str(header["source_type"]),
        source_doc_no_snapshot=header["source_doc_no_snapshot"],
        warehouse_id=int(header["warehouse_id"]),
        warehouse_name_snapshot=header["warehouse_name_snapshot"],
        supplier_id=header["supplier_id"],
        counterparty_name_snapshot=header["counterparty_name_snapshot"],
        status=str(header["status"]),
        remark=header["remark"],
        lines=lines,
    )


__all__ = [
    "list_inbound_tasks_repo",
    "get_inbound_task_repo",
]
