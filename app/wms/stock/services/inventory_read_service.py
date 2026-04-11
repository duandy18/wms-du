from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.stock.contracts.inventory import (
    InventoryDetailQuery,
    InventoryDetailResponse,
    InventoryDetailSlice,
    InventoryDetailTotals,
    InventoryQuery,
    InventoryResponse,
    InventoryRow,
)
from app.wms.stock.repos.inventory_read_repo import (
    query_inventory_detail_rows,
    query_inventory_rows,
)


class InventoryReadService:
    @staticmethod
    def _build_expiry_flags(expiry_date: date | None) -> tuple[bool, int | None]:
        if expiry_date is None:
            return False, None

        today = datetime.now(timezone.utc).date()
        near = expiry_date >= today and expiry_date <= (today + timedelta(days=30))
        days = int((expiry_date - today).days)
        return near, days

    @classmethod
    async def list_inventory(
        cls,
        session: AsyncSession,
        *,
        query: InventoryQuery,
    ) -> InventoryResponse:
        total, rows = await query_inventory_rows(
            session,
            q=query.q,
            item_id=query.item_id,
            warehouse_id=query.warehouse_id,
            lot_code=query.lot_code,
            near_expiry=query.near_expiry,
            offset=query.offset,
            limit=query.limit,
        )

        items: list[InventoryRow] = []
        for r in rows:
            expiry_date = r.get("expiry_date")
            near_expiry, days_to_expiry = cls._build_expiry_flags(expiry_date)
            items.append(
                InventoryRow(
                    item_id=int(r["item_id"]),
                    item_name=str(r["item_name"] or ""),
                    item_code=r.get("item_code"),
                    spec=r.get("spec"),
                    main_barcode=r.get("main_barcode"),
                    brand=r.get("brand"),
                    category=r.get("category"),
                    warehouse_id=int(r["warehouse_id"]),
                    lot_code=r.get("lot_code"),
                    production_date=r.get("production_date"),
                    qty=int(r["qty"] or 0),
                    expiry_date=expiry_date,
                    near_expiry=near_expiry,
                    days_to_expiry=days_to_expiry,
                )
            )

        return InventoryResponse(
            total=total,
            offset=query.offset,
            limit=query.limit,
            rows=items,
        )

    @classmethod
    async def get_inventory_detail(
        cls,
        session: AsyncSession,
        *,
        item_id: int,
        query: InventoryDetailQuery,
    ) -> InventoryDetailResponse:
        rows = await query_inventory_detail_rows(
            session,
            item_id=item_id,
            warehouse_id=query.warehouse_id,
            lot_code=query.lot_code,
        )

        if not rows:
            return InventoryDetailResponse(
                item_id=int(item_id),
                item_name="",
                totals=InventoryDetailTotals(
                    on_hand_qty=0,
                    available_qty=0,
                ),
                slices=[],
            )

        item_name = str(rows[0].get("item_name") or "")
        slices: list[InventoryDetailSlice] = []
        total_on_hand = 0

        for r in rows:
            qty = int(r.get("qty") or 0)
            expiry_date = r.get("expiry_date")
            near_expiry, _ = cls._build_expiry_flags(expiry_date)

            slices.append(
                InventoryDetailSlice(
                    warehouse_id=int(r["warehouse_id"]),
                    warehouse_name=str(r["warehouse_name"] or ""),
                    pool="MAIN",
                    lot_code=r.get("lot_code"),
                    production_date=r.get("production_date"),
                    expiry_date=expiry_date,
                    on_hand_qty=qty,
                    available_qty=qty,
                    near_expiry=near_expiry,
                    is_top=False,
                )
            )
            total_on_hand += qty

        ranked = sorted(
            list(enumerate(slices)),
            key=lambda x: x[1].on_hand_qty,
            reverse=True,
        )
        for idx, _slice in ranked[:2]:
            slices[idx].is_top = True

        return InventoryDetailResponse(
            item_id=int(item_id),
            item_name=item_name,
            totals=InventoryDetailTotals(
                on_hand_qty=total_on_hand,
                available_qty=total_on_hand,
            ),
            slices=slices,
        )


__all__ = ["InventoryReadService"]
