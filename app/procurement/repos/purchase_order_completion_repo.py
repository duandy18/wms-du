# app/procurement/repos/purchase_order_completion_repo.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def load_po_completion_head(
    session: AsyncSession,
    *,
    po_id: int,
) -> Optional[Dict[str, Any]]:
    sql = text(
        """
        SELECT
          po.id AS po_id,
          po.po_no AS po_no,
          po.status AS po_status,
          po.warehouse_id AS warehouse_id,
          po.supplier_id AS supplier_id,
          po.supplier_name AS supplier_name,
          po.purchaser AS purchaser,
          po.purchase_time AS purchase_time,
          po.total_amount AS total_amount,
          po.last_received_at AS po_last_received_at
        FROM purchase_orders po
        WHERE po.id = :po_id
        LIMIT 1
        """
    )
    row = (await session.execute(sql, {"po_id": int(po_id)})).mappings().first()
    return dict(row) if row is not None else None


async def list_po_completion_rows(
    session: AsyncSession,
    *,
    skip: int = 0,
    limit: int = 50,
    supplier_id: Optional[int] = None,
    po_status: Optional[str] = None,
    q: Optional[str] = None,
) -> List[Dict[str, Any]]:
    where_clauses: list[str] = []
    params: dict[str, Any] = {
        "skip": max(int(skip), 0),
        "limit": min(max(int(limit), 1), 200),
    }

    if supplier_id is not None:
        where_clauses.append("plc.supplier_id = :supplier_id")
        params["supplier_id"] = int(supplier_id)

    if po_status:
        where_clauses.append("po.status = :po_status")
        params["po_status"] = str(po_status).strip().upper()

    qv = (q or "").strip()
    if qv:
        where_clauses.append(
            """
            (
              plc.po_no ILIKE :q_like
              OR plc.supplier_name ILIKE :q_like
              OR COALESCE(plc.item_name, '') ILIKE :q_like
              OR COALESCE(plc.item_sku, '') ILIKE :q_like
            )
            """.strip()
        )
        params["q_like"] = f"%{qv}%"

    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)

    sql = text(
        f"""
        SELECT
          plc.po_id AS po_id,
          plc.po_no AS po_no,
          po.status AS po_status,
          plc.warehouse_id AS warehouse_id,
          plc.supplier_id AS supplier_id,
          plc.supplier_name AS supplier_name,
          plc.purchaser AS purchaser,
          plc.purchase_time AS purchase_time,
          po.total_amount AS total_amount,

          plc.po_line_id AS po_line_id,
          plc.line_no AS line_no,
          plc.item_id AS item_id,
          plc.item_name AS item_name,
          plc.item_sku AS item_sku,
          plc.spec_text AS spec_text,
          plc.purchase_uom_id_snapshot AS purchase_uom_id_snapshot,
          plc.purchase_uom_name_snapshot AS purchase_uom_name_snapshot,
          plc.purchase_ratio_to_base_snapshot AS purchase_ratio_to_base_snapshot,
          plc.qty_ordered_input AS qty_ordered_input,
          plc.qty_ordered_base AS qty_ordered_base,

          plc.qty_received_base AS qty_received_base,
          plc.qty_remaining_base AS qty_remaining_base,
          plc.line_completion_status AS line_completion_status,
          plc.last_received_at AS last_received_at
        FROM purchase_order_line_completion plc
        JOIN purchase_orders po
          ON po.id = plc.po_id
        {where_sql}
        ORDER BY plc.po_id DESC, plc.line_no ASC, plc.po_line_id ASC
        OFFSET :skip
        LIMIT :limit
        """
    )

    rows = (await session.execute(sql, params)).mappings().all()
    return [dict(r) for r in rows]


async def load_po_completion_rows(
    session: AsyncSession,
    *,
    po_id: int,
) -> List[Dict[str, Any]]:
    sql = text(
        """
        SELECT
          plc.po_line_id AS po_line_id,
          plc.line_no AS line_no,
          plc.item_id AS item_id,
          plc.item_name AS item_name,
          plc.item_sku AS item_sku,
          plc.spec_text AS spec_text,
          plc.purchase_uom_id_snapshot AS purchase_uom_id_snapshot,
          plc.purchase_uom_name_snapshot AS purchase_uom_name_snapshot,
          plc.purchase_ratio_to_base_snapshot AS purchase_ratio_to_base_snapshot,
          plc.qty_ordered_input AS qty_ordered_input,
          plc.qty_ordered_base AS qty_ordered_base,
          plc.qty_received_base AS qty_received_base,
          plc.qty_remaining_base AS qty_remaining_base,
          plc.line_completion_status AS line_completion_status,
          plc.last_received_at AS last_received_at
        FROM purchase_order_line_completion plc
        WHERE plc.po_id = :po_id
        ORDER BY plc.line_no ASC, plc.po_line_id ASC
        """
    )

    rows = (await session.execute(sql, {"po_id": int(po_id)})).mappings().all()
    return [dict(r) for r in rows]


async def load_po_completion_events(
    session: AsyncSession,
    *,
    po_id: int,
) -> List[Dict[str, Any]]:
    sql = text(
        """
        SELECT
          we.id AS event_id,
          we.event_no AS event_no,
          we.trace_id AS trace_id,
          we.source_ref AS source_ref,
          we.occurred_at AS occurred_at,

          iel.po_line_id AS po_line_id,
          pol.line_no AS line_no,
          iel.item_id AS item_id,

          iel.qty_base AS qty_base,
          iel.lot_code_input AS lot_code,
          iel.production_date AS production_date,
          iel.expiry_date AS expiry_date
        FROM inbound_event_lines iel
        JOIN wms_events we
          ON we.id = iel.event_id
        JOIN purchase_order_lines pol
          ON pol.id = iel.po_line_id
        WHERE pol.po_id = :po_id
          AND we.event_type = 'INBOUND'
          AND we.source_type = 'PURCHASE_ORDER'
          AND we.event_kind = 'COMMIT'
          AND we.status = 'COMMITTED'
        ORDER BY we.occurred_at DESC, we.id DESC, iel.line_no ASC
        """
    )

    rows = (await session.execute(sql, {"po_id": int(po_id)})).mappings().all()
    return [dict(r) for r in rows]


__all__ = [
    "load_po_completion_head",
    "list_po_completion_rows",
    "load_po_completion_rows",
    "load_po_completion_events",
]
