# app/procurement/services/purchase_order_completion.py
from __future__ import annotations

from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.procurement.contracts.purchase_order_completion import (
    PurchaseOrderCompletionDetailOut,
    PurchaseOrderCompletionEventOut,
    PurchaseOrderCompletionLineOut,
    PurchaseOrderCompletionListItemOut,
    PurchaseOrderCompletionSummaryOut,
)
from app.procurement.repos.purchase_order_completion_repo import (
    load_po_completion_events,
    load_po_completion_head,
    load_po_completion_rows,
    list_po_completion_rows,
)


def _derive_completion_status(*, qty_ordered_base: int, qty_received_base: int) -> str:
    ordered = max(int(qty_ordered_base), 0)
    received = max(int(qty_received_base), 0)

    if received <= 0:
        return "NOT_RECEIVED"
    if received < ordered:
        return "PARTIAL"
    return "RECEIVED"


class PurchaseOrderCompletionService:
    async def list_completion(
        self,
        session: AsyncSession,
        *,
        skip: int = 0,
        limit: int = 50,
        supplier_id: Optional[int] = None,
        po_status: Optional[str] = None,
        q: Optional[str] = None,
    ) -> List[PurchaseOrderCompletionListItemOut]:
        rows = await list_po_completion_rows(
            session,
            skip=skip,
            limit=limit,
            supplier_id=supplier_id,
            po_status=po_status,
            q=q,
        )

        out: List[PurchaseOrderCompletionListItemOut] = []
        for r in rows:
            out.append(
                PurchaseOrderCompletionListItemOut(
                    po_id=int(r["po_id"]),
                    po_no=str(r["po_no"]),
                    po_status=str(r["po_status"]),
                    warehouse_id=int(r["warehouse_id"]),
                    supplier_id=int(r["supplier_id"]),
                    supplier_name=str(r["supplier_name"]),
                    purchaser=str(r["purchaser"]),
                    purchase_time=r["purchase_time"],
                    total_amount=r.get("total_amount"),
                    po_line_id=int(r["po_line_id"]),
                    line_no=int(r["line_no"]),
                    item_id=int(r["item_id"]),
                    item_name=r.get("item_name"),
                    item_sku=r.get("item_sku"),
                    spec_text=r.get("spec_text"),
                    purchase_uom_id_snapshot=int(r["purchase_uom_id_snapshot"]),
                    purchase_uom_name_snapshot=str(r["purchase_uom_name_snapshot"]),
                    purchase_ratio_to_base_snapshot=int(r["purchase_ratio_to_base_snapshot"]),
                    qty_ordered_input=int(r["qty_ordered_input"]),
                    qty_ordered_base=int(r["qty_ordered_base"]),
                    qty_received_base=int(r["qty_received_base"]),
                    qty_remaining_base=int(r["qty_remaining_base"]),
                    line_completion_status=str(r["line_completion_status"]),
                    last_received_at=r.get("last_received_at"),
                )
            )
        return out

    async def get_completion_detail(
        self,
        session: AsyncSession,
        *,
        po_id: int,
    ) -> PurchaseOrderCompletionDetailOut:
        head = await load_po_completion_head(session, po_id=po_id)
        if head is None:
            raise ValueError("PurchaseOrder not found")

        rows = await load_po_completion_rows(session, po_id=po_id)
        events = await load_po_completion_events(session, po_id=po_id)

        line_out: List[PurchaseOrderCompletionLineOut] = []
        total_ordered_base = 0
        total_received_base = 0
        total_remaining_base = 0
        max_last_received_at = head.get("po_last_received_at")

        for r in rows:
            ordered = int(r["qty_ordered_base"])
            received = int(r["qty_received_base"])
            remaining = int(r["qty_remaining_base"])

            total_ordered_base += ordered
            total_received_base += received
            total_remaining_base += remaining

            last_received_at = r.get("last_received_at")
            if last_received_at is not None and (
                max_last_received_at is None or last_received_at > max_last_received_at
            ):
                max_last_received_at = last_received_at

            line_out.append(
                PurchaseOrderCompletionLineOut(
                    po_line_id=int(r["po_line_id"]),
                    line_no=int(r["line_no"]),
                    item_id=int(r["item_id"]),
                    item_name=r.get("item_name"),
                    item_sku=r.get("item_sku"),
                    spec_text=r.get("spec_text"),
                    purchase_uom_id_snapshot=int(r["purchase_uom_id_snapshot"]),
                    purchase_uom_name_snapshot=str(r["purchase_uom_name_snapshot"]),
                    purchase_ratio_to_base_snapshot=int(r["purchase_ratio_to_base_snapshot"]),
                    qty_ordered_input=int(r["qty_ordered_input"]),
                    qty_ordered_base=ordered,
                    qty_received_base=received,
                    qty_remaining_base=remaining,
                    line_completion_status=str(r["line_completion_status"]),
                    last_received_at=last_received_at,
                )
            )

        summary = PurchaseOrderCompletionSummaryOut(
            po_id=int(head["po_id"]),
            po_no=str(head["po_no"]),
            po_status=str(head["po_status"]),
            warehouse_id=int(head["warehouse_id"]),
            supplier_id=int(head["supplier_id"]),
            supplier_name=str(head["supplier_name"]),
            purchaser=str(head["purchaser"]),
            purchase_time=head["purchase_time"],
            total_amount=head.get("total_amount"),
            total_ordered_base=int(total_ordered_base),
            total_received_base=int(total_received_base),
            total_remaining_base=int(total_remaining_base),
            completion_status=_derive_completion_status(
                qty_ordered_base=int(total_ordered_base),
                qty_received_base=int(total_received_base),
            ),
            last_received_at=max_last_received_at,
        )

        event_out = [
            PurchaseOrderCompletionEventOut(
                event_id=int(r["event_id"]),
                event_no=str(r["event_no"]),
                trace_id=str(r["trace_id"]),
                source_ref=r.get("source_ref"),
                occurred_at=r["occurred_at"],
                po_line_id=int(r["po_line_id"]),
                line_no=int(r["line_no"]),
                item_id=int(r["item_id"]),
                qty_base=int(r["qty_base"]),
                lot_code=r.get("lot_code"),
                production_date=r.get("production_date"),
                expiry_date=r.get("expiry_date"),
            )
            for r in events
        ]

        return PurchaseOrderCompletionDetailOut(
            summary=summary,
            lines=line_out,
            receipt_events=event_out,
        )


__all__ = ["PurchaseOrderCompletionService"]
