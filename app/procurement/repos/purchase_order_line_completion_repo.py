# app/procurement/repos/purchase_order_line_completion_repo.py
from __future__ import annotations

from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def upsert_completion_rows_for_po(
    session: AsyncSession,
    *,
    po_id: int,
) -> None:
    """
    以 purchase_order_lines 为主体，初始化 / 重建该采购单的 completion 读表行。

    当前第一阶段主要用于：
    - 创建采购单后初始化 completion 行
    - 后续若采购单支持编辑，可复用为“按当前快照重建”
    """
    sql = text(
        """
        INSERT INTO purchase_order_line_completion (
          po_line_id,
          po_id,
          po_no,
          line_no,
          warehouse_id,
          supplier_id,
          supplier_name,
          purchaser,
          purchase_time,
          item_id,
          item_name,
          item_sku,
          spec_text,
          purchase_uom_id_snapshot,
          purchase_uom_name_snapshot,
          purchase_ratio_to_base_snapshot,
          qty_ordered_input,
          qty_ordered_base,
          supply_price_snapshot,
          planned_line_amount,
          qty_received_base,
          qty_remaining_base,
          line_completion_status,
          last_received_at
        )
        SELECT
          pol.id AS po_line_id,
          po.id AS po_id,
          po.po_no AS po_no,
          pol.line_no AS line_no,
          po.warehouse_id AS warehouse_id,
          po.supplier_id AS supplier_id,
          po.supplier_name AS supplier_name,
          po.purchaser AS purchaser,
          po.purchase_time AS purchase_time,
          pol.item_id AS item_id,
          pol.item_name AS item_name,
          pol.item_sku AS item_sku,
          pol.spec_text AS spec_text,
          pol.purchase_uom_id_snapshot AS purchase_uom_id_snapshot,
          COALESCE(iu.display_name, iu.uom) AS purchase_uom_name_snapshot,
          pol.purchase_ratio_to_base_snapshot AS purchase_ratio_to_base_snapshot,
          pol.qty_ordered_input AS qty_ordered_input,
          pol.qty_ordered_base AS qty_ordered_base,
          pol.supply_price AS supply_price_snapshot,
          (
            COALESCE(pol.supply_price, 0::numeric(12, 2)) * pol.qty_ordered_base
          )::numeric(14, 2) AS planned_line_amount,
          0 AS qty_received_base,
          pol.qty_ordered_base AS qty_remaining_base,
          'NOT_RECEIVED' AS line_completion_status,
          NULL AS last_received_at
        FROM purchase_order_lines pol
        JOIN purchase_orders po
          ON po.id = pol.po_id
        JOIN item_uoms iu
          ON iu.id = pol.purchase_uom_id_snapshot
        WHERE po.id = :po_id
        ON CONFLICT (po_line_id) DO UPDATE
        SET
          po_id = EXCLUDED.po_id,
          po_no = EXCLUDED.po_no,
          line_no = EXCLUDED.line_no,
          warehouse_id = EXCLUDED.warehouse_id,
          supplier_id = EXCLUDED.supplier_id,
          supplier_name = EXCLUDED.supplier_name,
          purchaser = EXCLUDED.purchaser,
          purchase_time = EXCLUDED.purchase_time,
          item_id = EXCLUDED.item_id,
          item_name = EXCLUDED.item_name,
          item_sku = EXCLUDED.item_sku,
          spec_text = EXCLUDED.spec_text,
          purchase_uom_id_snapshot = EXCLUDED.purchase_uom_id_snapshot,
          purchase_uom_name_snapshot = EXCLUDED.purchase_uom_name_snapshot,
          purchase_ratio_to_base_snapshot = EXCLUDED.purchase_ratio_to_base_snapshot,
          qty_ordered_input = EXCLUDED.qty_ordered_input,
          qty_ordered_base = EXCLUDED.qty_ordered_base,
          supply_price_snapshot = EXCLUDED.supply_price_snapshot,
          planned_line_amount = EXCLUDED.planned_line_amount,
          qty_remaining_base = GREATEST(
            EXCLUDED.qty_ordered_base - purchase_order_line_completion.qty_received_base,
            0
          ),
          line_completion_status = CASE
            WHEN purchase_order_line_completion.qty_received_base <= 0 THEN 'NOT_RECEIVED'
            WHEN purchase_order_line_completion.qty_received_base < EXCLUDED.qty_ordered_base THEN 'PARTIAL'
            ELSE 'RECEIVED'
          END,
          updated_at = now()
        """
    )
    await session.execute(sql, {"po_id": int(po_id)})


async def rebuild_completion_rows_for_po(
    session: AsyncSession,
    *,
    po_id: int,
) -> None:
    """
    预留给后续采购单编辑路径使用：
    - 先删该单所有 completion 行
    - 再按当前头/行快照整体重建
    """
    await session.execute(
        text("DELETE FROM purchase_order_line_completion WHERE po_id = :po_id"),
        {"po_id": int(po_id)},
    )
    await upsert_completion_rows_for_po(session, po_id=po_id)


async def apply_completion_delta_for_event(
    session: AsyncSession,
    *,
    event_id: int,
    occurred_at: datetime,
) -> None:
    """
    针对一次正式采购入库事件，按 event_id 聚合本次新增 qty_base，
    并增量更新 completion 读表。

    要求：
    - 调用方应保证 event / inbound_event_lines 已 flush
    - 仅采购来源 event line 才会带 po_line_id
    """
    sql = text(
        """
        WITH delta AS (
          SELECT
            iel.po_line_id AS po_line_id,
            SUM(iel.qty_base)::int AS add_qty
          FROM inbound_event_lines iel
          WHERE iel.event_id = :event_id
            AND iel.po_line_id IS NOT NULL
          GROUP BY iel.po_line_id
        )
        UPDATE purchase_order_line_completion plc
        SET
          qty_received_base = plc.qty_received_base + d.add_qty,
          qty_remaining_base = GREATEST(
            plc.qty_ordered_base - (plc.qty_received_base + d.add_qty),
            0
          ),
          line_completion_status = CASE
            WHEN (plc.qty_received_base + d.add_qty) <= 0 THEN 'NOT_RECEIVED'
            WHEN (plc.qty_received_base + d.add_qty) < plc.qty_ordered_base THEN 'PARTIAL'
            ELSE 'RECEIVED'
          END,
          last_received_at = CASE
            WHEN plc.last_received_at IS NULL OR plc.last_received_at < :occurred_at
              THEN :occurred_at
            ELSE plc.last_received_at
          END,
          updated_at = now()
        FROM delta d
        WHERE plc.po_line_id = d.po_line_id
        """
    )
    await session.execute(
        sql,
        {
            "event_id": int(event_id),
            "occurred_at": occurred_at,
        },
    )


__all__ = [
    "upsert_completion_rows_for_po",
    "rebuild_completion_rows_for_po",
    "apply_completion_delta_for_event",
]
