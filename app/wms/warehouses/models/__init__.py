# app/wms/warehouses/models/__init__.py
# Domain-owned ORM models for WMS warehouses.

from app.wms.warehouses.models.warehouse import Warehouse, WarehouseCode

__all__ = [
    "Warehouse",
    "WarehouseCode",
]
