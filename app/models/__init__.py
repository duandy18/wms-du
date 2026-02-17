# app/models/__init__.py
"""
统一导出 ORM 模型（主线模型）。

⚠️ 重要：
- 加载顺序非常关键。
- 所有被 relationship("ClassName") 字符串引用的类，
  必须在引用方之前被注册。
"""

from importlib import import_module


def _export(module_name: str, class_name: str) -> None:
    module = import_module(module_name)
    globals()[class_name] = getattr(module, class_name)


MODEL_SPECS = [
    # ------------------------------------------------------------------
    # 主数据（必须最早加载，供其它模型 relationship 引用）
    # ------------------------------------------------------------------
    ("app.models.supplier", "Supplier"),
    ("app.models.supplier_contact", "SupplierContact"),

    # ⚠️ 关键顺序：先加载 WarehouseShippingProvider
    # 再加载 ShippingProvider / Warehouse
    ("app.models.warehouse_shipping_provider", "WarehouseShippingProvider"),

    ("app.models.shipping_provider", "ShippingProvider"),
    ("app.models.shipping_provider_contact", "ShippingProviderContact"),

    # ------------------------------------------------------------------
    # 仓库 / 基础库存模型
    # ------------------------------------------------------------------
    ("app.models.warehouse", "Warehouse"),
    ("app.models.location", "Location"),

    ("app.models.item", "Item"),
    ("app.models.item_test_set", "ItemTestSet"),
    ("app.models.item_test_set_item", "ItemTestSetItem"),

    ("app.models.batch", "Batch"),
    ("app.models.stock", "Stock"),
    ("app.models.stock_ledger", "StockLedger"),
    ("app.models.stock_snapshot", "StockSnapshot"),

    # ------------------------------------------------------------------
    # 订单 & 出库
    # ------------------------------------------------------------------
    ("app.models.order", "Order"),
    ("app.models.order_item", "OrderItem"),
    ("app.models.order_line", "OrderLine"),
    ("app.models.order_logistics", "OrderLogistics"),
    ("app.models.order_state_snapshot", "OrderStateSnapshot"),

    # 拣货任务
    ("app.models.pick_task", "PickTask"),
    ("app.models.pick_task_line", "PickTaskLine"),

    # ------------------------------------------------------------------
    # 平台 & 事件
    # ------------------------------------------------------------------
    ("app.models.platform_shops", "PlatformShop"),
    ("app.models.platform_event", "PlatformEvent"),
    ("app.models.event_store", "EventStore"),
    ("app.models.event_log", "EventLog"),
    ("app.models.event_error_log", "EventErrorLog"),
    ("app.models.audit_event", "AuditEvent"),

    # ------------------------------------------------------------------
    # 门店 & RBAC
    # ------------------------------------------------------------------
    ("app.models.store", "Store"),
    ("app.models.user", "User"),
    ("app.models.role", "Role"),
    ("app.models.permission", "Permission"),

    # ------------------------------------------------------------------
    # 采购系统
    # ------------------------------------------------------------------
    ("app.models.purchase_order", "PurchaseOrder"),
    ("app.models.purchase_order_line", "PurchaseOrderLine"),

    # ------------------------------------------------------------------
    # 收货事实（唯一模型）
    # ------------------------------------------------------------------
    ("app.models.inbound_receipt", "InboundReceipt"),
    ("app.models.inbound_receipt", "InboundReceiptLine"),

    # ------------------------------------------------------------------
    # 退货任务
    # ------------------------------------------------------------------
    ("app.models.return_task", "ReturnTask"),
    ("app.models.return_task", "ReturnTaskLine"),

    # ------------------------------------------------------------------
    # 内部出库
    # ------------------------------------------------------------------
    ("app.models.internal_outbound", "InternalOutboundDoc"),
    ("app.models.internal_outbound", "InternalOutboundLine"),

    # ------------------------------------------------------------------
    # 运价（结构化 Pricing）
    # ------------------------------------------------------------------
    ("app.models.shipping_provider_pricing_scheme", "ShippingProviderPricingScheme"),
    ("app.models.shipping_provider_zone", "ShippingProviderZone"),
    ("app.models.shipping_provider_zone_member", "ShippingProviderZoneMember"),
    ("app.models.shipping_provider_zone_bracket", "ShippingProviderZoneBracket"),
    ("app.models.shipping_provider_surcharge", "ShippingProviderSurcharge"),
]


# 实际导出
for _module, _name in MODEL_SPECS:
    _export(_module, _name)


# 有些模型提供 table 对象
from app.models.batch import Batch as _Batch  # noqa: E402

Batches = getattr(_Batch, "__table__", None)


__all__ = [
    # ---- Master Data ----
    "Supplier",
    "SupplierContact",
    "WarehouseShippingProvider",
    "ShippingProvider",
    "ShippingProviderContact",

    # ---- Inventory ----
    "Warehouse",
    "Location",
    "Item",
    "ItemTestSet",
    "ItemTestSetItem",
    "Batch",
    "Stock",
    "StockLedger",
    "StockSnapshot",

    # ---- Orders ----
    "Order",
    "OrderItem",
    "OrderLine",
    "OrderLogistics",
    "OrderStateSnapshot",

    # ---- Pick Tasks ----
    "PickTask",
    "PickTaskLine",

    # ---- Events ----
    "PlatformShop",
    "PlatformEvent",
    "EventStore",
    "EventLog",
    "EventErrorLog",
    "AuditEvent",

    # ---- Store & RBAC ----
    "Store",
    "User",
    "Role",
    "Permission",

    # ---- Purchase ----
    "PurchaseOrder",
    "PurchaseOrderLine",

    # ---- Inbound ----
    "InboundReceipt",
    "InboundReceiptLine",

    # ---- Return ----
    "ReturnTask",
    "ReturnTaskLine",

    # ---- Internal Outbound ----
    "InternalOutboundDoc",
    "InternalOutboundLine",

    # ---- Pricing ----
    "ShippingProviderPricingScheme",
    "ShippingProviderZone",
    "ShippingProviderZoneMember",
    "ShippingProviderZoneBracket",
    "ShippingProviderSurcharge",

    "Batches",
]
