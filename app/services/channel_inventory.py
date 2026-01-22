from __future__ import annotations

# Legacy shim (Phase 4.x hard cut):
# - keep file path stable if someone references it
# - DO NOT provide ChannelInventoryService anymore



from app.services.channel_inventory_types import BatchQty, ChannelInventory
from app.services.inventory_view_service import InventoryViewService


__all__ = ["BatchQty", "ChannelInventory", "InventoryViewService"]
