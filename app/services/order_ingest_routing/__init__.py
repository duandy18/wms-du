# app/services/order_ingest_routing/__init__.py
from __future__ import annotations

from .route_c import auto_route_warehouse_if_possible

__all__ = ["auto_route_warehouse_if_possible"]
