# app/services/channel_inventory_service.py
from __future__ import annotations

"""
⚠️ Phase 4.x：渠道库存（ChannelInventory）不再是库存事实层。

本模块已被废弃，不再提供任何服务类。

请使用：
- 事实层：app.services.stock_availability_service.StockAvailabilityService
- 整单履约裁决：app.services.warehouse_router.WarehouseRouter
- 展示视图：app.services.inventory_view_service.InventoryViewService
"""

# 这里刻意不提供旧类名，防止旧入口继续存在。
__all__: list[str] = []
