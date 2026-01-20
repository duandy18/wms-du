# app/api/routers/channel_inventory.py
from __future__ import annotations

from fastapi import APIRouter

from app.api.routers import channel_inventory_routes
from app.api.routers.channel_inventory_mappers import (
    map_multi as _map_multi,
    map_single as _map_single,
)
from app.api.routers.channel_inventory_schemas import (
    BatchQtyModel,
    ChannelInventoryModel,
    ChannelInventoryMultiModel,
    WarehouseInventoryModel,
)

router = APIRouter(prefix="/global-available", tags=["global-available"])


def _register_all_routes() -> None:
    channel_inventory_routes.register(router)


_register_all_routes()

__all__ = [
    "router",
    "BatchQtyModel",
    "ChannelInventoryModel",
    "WarehouseInventoryModel",
    "ChannelInventoryMultiModel",
    "_map_single",
    "_map_multi",
]
