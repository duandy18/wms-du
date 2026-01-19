from __future__ import annotations

# 稳定门面：保留历史 import 路径，实际实现位于 app/services/order_ingest_routing/。

from app.services.order_ingest_routing.route_c import auto_route_warehouse_if_possible

__all__ = ["auto_route_warehouse_if_possible"]
