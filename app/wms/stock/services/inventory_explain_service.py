from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.ledger.helpers.stock_ledger import infer_movement_type
from app.wms.stock.contracts.inventory_explain import (
    InventoryExplainAnchor,
    InventoryExplainIn,
    InventoryExplainLedgerRow,
    InventoryExplainOut,
    InventoryExplainSummary,
)
from app.wms.stock.repos.inventory_explain_repo import (
    count_inventory_explain_ledger_rows,
    query_inventory_explain_latest_after_qty,
    query_inventory_explain_ledger_rows,
    resolve_inventory_explain_anchor,
)


class InventoryExplainService:
    @classmethod
    async def explain_inventory(
        cls,
        session: AsyncSession,
        *,
        payload: InventoryExplainIn,
    ) -> InventoryExplainOut:
        try:
            anchor_row = await resolve_inventory_explain_anchor(
                session,
                item_id=payload.item_id,
                warehouse_id=payload.warehouse_id,
                lot_id=payload.lot_id,
                lot_code=payload.lot_code,
            )
        except RuntimeError as exc:
            if str(exc) == "ambiguous_inventory_explain_anchor":
                raise HTTPException(
                    status_code=409,
                    detail="当前库存锚点不唯一，请优先传 lot_id。",
                ) from exc
            raise

        if anchor_row is None:
            raise HTTPException(
                status_code=404,
                detail="未找到对应的当前库存槽位，或该槽位已无余额。",
            )

        resolved_lot_id = int(anchor_row["lot_id"])
        total_rows = await count_inventory_explain_ledger_rows(
            session,
            item_id=payload.item_id,
            warehouse_id=payload.warehouse_id,
            lot_id=resolved_lot_id,
        )

        raw_rows = await query_inventory_explain_ledger_rows(
            session,
            item_id=payload.item_id,
            warehouse_id=payload.warehouse_id,
            lot_id=resolved_lot_id,
            limit=payload.limit,
        )

        ledger_rows = [
            InventoryExplainLedgerRow(
                id=int(r["id"]),
                occurred_at=r["occurred_at"],
                created_at=r["created_at"],
                reason=str(r["reason"]),
                reason_canon=r.get("reason_canon"),
                sub_reason=r.get("sub_reason"),
                ref=str(r["ref"]),
                ref_line=int(r["ref_line"]),
                delta=int(r["delta"]),
                after_qty=int(r["after_qty"]),
                trace_id=r.get("trace_id"),
                movement_type=infer_movement_type(r.get("reason")),
                item_id=int(r["item_id"]),
                item_name=r.get("item_name"),
                warehouse_id=int(r["warehouse_id"]),
                lot_id=int(r["lot_id"]) if r.get("lot_id") is not None else None,
                lot_code=r.get("lot_code"),
                base_item_uom_id=(
                    int(r["base_item_uom_id"])
                    if r.get("base_item_uom_id") is not None
                    else None
                ),
                base_uom_name=r.get("base_uom_name"),
            )
            for r in raw_rows
        ]

        latest_after_qty = await query_inventory_explain_latest_after_qty(
            session,
            item_id=payload.item_id,
            warehouse_id=payload.warehouse_id,
            lot_id=resolved_lot_id,
        )

        current_qty = int(anchor_row["current_qty"])

        return InventoryExplainOut(
            anchor=InventoryExplainAnchor(
                item_id=int(anchor_row["item_id"]),
                item_name=str(anchor_row["item_name"] or ""),
                warehouse_id=int(anchor_row["warehouse_id"]),
                warehouse_name=str(anchor_row["warehouse_name"] or ""),
                lot_id=resolved_lot_id,
                lot_code=anchor_row.get("lot_code"),
                base_item_uom_id=(
                    int(anchor_row["base_item_uom_id"])
                    if anchor_row.get("base_item_uom_id") is not None
                    else None
                ),
                base_uom_name=anchor_row.get("base_uom_name"),
                current_qty=current_qty,
            ),
            ledger_rows=ledger_rows,
            summary=InventoryExplainSummary(
                row_count=total_rows,
                truncated=total_rows > len(ledger_rows),
                current_qty=current_qty,
                ledger_last_after_qty=latest_after_qty,
                matches_current=(
                    bool(latest_after_qty == current_qty)
                    if latest_after_qty is not None
                    else None
                ),
            ),
        )
