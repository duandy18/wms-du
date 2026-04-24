from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.inventory_adjustment.summary.contracts.summary import (
    InventoryAdjustmentSummaryDetailOut,
    InventoryAdjustmentSummaryLedgerRowOut,
    InventoryAdjustmentSummaryListOut,
    InventoryAdjustmentSummaryRowOut,
)
from app.wms.inventory_adjustment.summary.repos.summary_repo import (
    get_inventory_adjustment_summary_row,
    list_inventory_adjustment_summary_ledger_rows,
    list_inventory_adjustment_summary_rows,
)


async def list_inventory_adjustment_summary(
    session: AsyncSession,
    *,
    adjustment_type: str | None = None,
    warehouse_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> InventoryAdjustmentSummaryListOut:
    total, rows = await list_inventory_adjustment_summary_rows(
        session,
        adjustment_type=adjustment_type,
        warehouse_id=warehouse_id,
        limit=int(limit),
        offset=int(offset),
    )

    return InventoryAdjustmentSummaryListOut(
        items=[InventoryAdjustmentSummaryRowOut(**row) for row in rows],
        total=int(total),
        limit=int(limit),
        offset=int(offset),
    )



async def get_inventory_adjustment_summary_detail(
    session: AsyncSession,
    *,
    adjustment_type: str,
    object_id: int,
) -> InventoryAdjustmentSummaryDetailOut:
    row = await get_inventory_adjustment_summary_row(
        session,
        adjustment_type=adjustment_type,
        object_id=int(object_id),
    )
    if row is None:
        raise LookupError(
            f"inventory_adjustment_summary_not_found:{str(adjustment_type).strip().upper()}:{int(object_id)}"
        )

    ledger_rows = await list_inventory_adjustment_summary_ledger_rows(
        session,
        adjustment_type=adjustment_type,
        object_id=int(object_id),
    )

    return InventoryAdjustmentSummaryDetailOut(
        row=InventoryAdjustmentSummaryRowOut(**row),
        ledger_rows=[InventoryAdjustmentSummaryLedgerRowOut(**x) for x in ledger_rows],
    )


__all__ = [
    "list_inventory_adjustment_summary",
    "get_inventory_adjustment_summary_detail",
]
