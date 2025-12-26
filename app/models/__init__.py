# app/models/__init__.py
"""
统一导出 ORM 模型（主线模型，不包含已归档 / 兼容层）。
"""

from importlib import import_module


def _export(module_name: str, class_name: str) -> None:
    module = import_module(module_name)
    globals()[class_name] = getattr(module, class_name)


MODEL_SPECS = [
    # -------- 库存 / 批次 --------
    ("app.models.item", "Item"),
    ("app.models.location", "Location"),
    ("app.models.warehouse", "Warehouse"),
    ("app.models.batch", "Batch"),
    ("app.models.stock", "Stock"),
    ("app.models.stock_ledger", "StockLedger"),
    ("app.models.stock_snapshot", "StockSnapshot"),
    # -------- 订单 & 出库相关（v2/v3）--------
    ("app.models.order", "Order"),
    ("app.models.order_item", "OrderItem"),
    ("app.models.order_line", "OrderLine"),
    ("app.models.order_logistics", "OrderLogistics"),
    ("app.models.order_state_snapshot", "OrderStateSnapshot"),
    # -------- 拣货任务 --------
    ("app.models.pick_task", "PickTask"),
    ("app.models.pick_task_line", "PickTaskLine"),
    # -------- 平台 & 事件流 --------
    ("app.models.platform_shops", "PlatformShop"),
    ("app.models.platform_event", "PlatformEvent"),
    ("app.models.event_store", "EventStore"),
    ("app.models.event_log", "EventLog"),
    ("app.models.event_error_log", "EventErrorLog"),
    ("app.models.audit_event", "AuditEvent"),
    # -------- 预占 / 软预占 --------
    ("app.models.reservation", "Reservation"),
    ("app.models.reservation_line", "ReservationLine"),
    ("app.models.reservation_allocation", "ReservationAllocations"),
    # -------- 门店 & RBAC --------
    ("app.models.store", "Store"),
    ("app.models.user", "User"),
    ("app.models.role", "Role"),
    ("app.models.permission", "Permission"),
    # -------- 采购系统 --------
    ("app.models.purchase_order", "PurchaseOrder"),
    ("app.models.purchase_order_line", "PurchaseOrderLine"),
    # -------- 收货任务 --------
    ("app.models.receive_task", "ReceiveTask"),
    ("app.models.receive_task", "ReceiveTaskLine"),
    # -------- 退货任务（采购退货）--------
    ("app.models.return_task", "ReturnTask"),
    ("app.models.return_task", "ReturnTaskLine"),
    # -------- 内部出库（Internal Outbound）--------
    ("app.models.internal_outbound", "InternalOutboundDoc"),
    ("app.models.internal_outbound", "InternalOutboundLine"),
    # -------- 主数据 --------
    ("app.models.supplier", "Supplier"),
    ("app.models.supplier_contact", "SupplierContact"),
    ("app.models.shipping_provider", "ShippingProvider"),
    ("app.models.shipping_provider_contact", "ShippingProviderContact"),
    # -------- 运价（Phase 3 延展：结构化 Pricing）--------
    ("app.models.shipping_provider_pricing_scheme", "ShippingProviderPricingScheme"),
    ("app.models.shipping_provider_zone", "ShippingProviderZone"),
    ("app.models.shipping_provider_zone_member", "ShippingProviderZoneMember"),
    ("app.models.shipping_provider_zone_bracket", "ShippingProviderZoneBracket"),
    ("app.models.shipping_provider_surcharge", "ShippingProviderSurcharge"),
]

for _module, _name in MODEL_SPECS:
    _export(_module, _name)

# 额外导出的表（有些模型提供 table 对象）
from app.models.batch import Batch as _Batch  # noqa: E402
from app.models.reservation_allocation import (  # noqa: E402
    ReservationAllocations as _ReservationAllocations,
)

Batches = getattr(_Batch, "__table__", None)
ReservationAllocations = getattr(_ReservationAllocations, "__table__", None)

__all__ = [
    "Item",
    "Location",
    "Warehouse",
    "Batch",
    "Stock",
    "StockLedger",
    "StockSnapshot",
    "Order",
    "OrderItem",
    "OrderLine",
    "OrderLogistics",
    "OrderStateSnapshot",
    "PickTask",
    "PickTaskLine",
    "PlatformShop",
    "PlatformEvent",
    "EventStore",
    "EventLog",
    "EventErrorLog",
    "AuditEvent",
    "Reservation",
    "ReservationLine",
    "ReservationAllocations",
    "Store",
    "User",
    "Role",
    "Permission",
    "PurchaseOrder",
    "PurchaseOrderLine",
    "ReceiveTask",
    "ReceiveTaskLine",
    "ReturnTask",
    "ReturnTaskLine",
    # ---- Internal Outbound ----
    "InternalOutboundDoc",
    "InternalOutboundLine",
    # ---- Master Data ----
    "Supplier",
    "SupplierContact",
    "ShippingProvider",
    "ShippingProviderContact",
    # ---- Pricing ----
    "ShippingProviderPricingScheme",
    "ShippingProviderZone",
    "ShippingProviderZoneMember",
    "ShippingProviderZoneBracket",
    "ShippingProviderSurcharge",
    "Batches",
    "ReservationAllocations",
]
