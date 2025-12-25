# app/api/routers/channel_inventory_mappers.py
from __future__ import annotations

from typing import Dict, List, Optional

from app.services.channel_inventory_service import ChannelInventory

from app.api.routers.channel_inventory_schemas import (
    BatchQtyModel,
    ChannelInventoryModel,
    ChannelInventoryMultiModel,
    WarehouseInventoryModel,
)


def map_single(ci: ChannelInventory) -> ChannelInventoryModel:
    return ChannelInventoryModel(
        platform=ci.platform,
        shop_id=ci.shop_id,
        warehouse_id=ci.warehouse_id,
        item_id=ci.item_id,
        on_hand=ci.on_hand,
        reserved_open=ci.reserved_open,
        available=ci.available,
        batches=[BatchQtyModel(batch_code=b.batch_code, qty=b.qty) for b in ci.batches],
    )


def map_multi(
    platform: str,
    shop_id: str,
    item_id: int,
    lst: List[ChannelInventory],
    bindings_by_wh: Optional[Dict[int, Dict[str, object]]] = None,
) -> ChannelInventoryMultiModel:
    warehouses: List[WarehouseInventoryModel] = []

    for ci in lst:
        meta = bindings_by_wh.get(ci.warehouse_id) if bindings_by_wh else None
        warehouses.append(
            WarehouseInventoryModel(
                warehouse_id=ci.warehouse_id,
                on_hand=ci.on_hand,
                reserved_open=ci.reserved_open,
                available=ci.available,
                batches=[BatchQtyModel(batch_code=b.batch_code, qty=b.qty) for b in ci.batches],
                is_top=bool(meta.get("is_top")) if meta else False,
                is_default=bool(meta.get("is_default")) if meta else False,
                priority=int(meta.get("priority"))
                if meta and meta.get("priority") is not None
                else 100,
            )
        )

    return ChannelInventoryMultiModel(
        platform=platform,
        shop_id=shop_id,
        item_id=item_id,
        warehouses=warehouses,
    )
