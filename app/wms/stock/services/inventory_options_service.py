from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.stock.contracts.options import (
    InventoryItemOption,
    InventoryOptionsQuery,
    InventoryOptionsResponse,
    InventoryWarehouseOption,
)
from app.wms.stock.repos.inventory_options_repo import (
    list_active_warehouses,
    list_public_items,
)


class InventoryOptionsService:
    @classmethod
    async def get_options(
        cls,
        session: AsyncSession,
        *,
        query: InventoryOptionsQuery,
    ) -> InventoryOptionsResponse:
        warehouses_raw = await list_active_warehouses(
            session,
            active_only=query.warehouses_active_only,
        )
        items_raw = await list_public_items(
            session,
            q=query.item_q,
            limit=query.item_limit,
        )

        return InventoryOptionsResponse(
            warehouses=[
                InventoryWarehouseOption(
                    id=int(r["id"]),
                    name=str(r["name"] or ""),
                    code=r.get("code"),
                    active=bool(r.get("active")),
                )
                for r in warehouses_raw
            ],
            items=[
                InventoryItemOption(
                    id=int(r["id"]),
                    sku=str(r["sku"] or ""),
                    name=str(r["name"] or ""),
                )
                for r in items_raw
            ],
        )


__all__ = ["InventoryOptionsService"]
