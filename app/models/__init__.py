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
    ("app.pms.suppliers.models.supplier", "Supplier"),
    ("app.pms.suppliers.models.supplier_contact", "SupplierContact"),
    # ⚠️ 关键顺序：先加载 WarehouseShippingProvider
    # 再加载 ShippingProvider / Warehouse
    ("app.models.warehouse_shipping_provider", "WarehouseShippingProvider"),
    ("app.models.shipping_provider", "ShippingProvider"),
    ("app.models.shipping_provider_contact", "ShippingProviderContact"),
    ("app.models.electronic_waybill_config", "ElectronicWaybillConfig"),
    # ------------------------------------------------------------------
    # 仓库 / 基础库存模型
    # ------------------------------------------------------------------
    ("app.models.warehouse", "Warehouse"),
    # ✅ 旧“库位维度”已从主线移除（库存主链路仅使用 warehouse_id）
    ("app.pms.items.models.item", "Item"),
    # ✅ Phase M-2：多包装/多单位结构化
    ("app.pms.items.models.item_uom", "ItemUOM"),
    ("app.models.item_test_set", "ItemTestSet"),
    ("app.models.item_test_set_item", "ItemTestSetItem"),
    ("app.wms.stock.models.lot", "Lot"),
    # ✅ Phase 5：lot-world 成为唯一库存余额真相（stocks_lot + lots）
    ("app.wms.stock.models.stock_lot", "StockLot"),
    ("app.wms.ledger.models.stock_ledger", "StockLedger"),
    ("app.wms.stock.models.stock_snapshot", "StockSnapshot"),
    # ------------------------------------------------------------------
    # WMS 统一事件头 + 入库事件行
    # ------------------------------------------------------------------
    ("app.wms.inbound.models.inbound_event", "WmsEvent"),
    ("app.wms.inbound.models.inbound_event", "InboundEventLine"),
    # ------------------------------------------------------------------
    # 订单 & 出库
    # ------------------------------------------------------------------
    ("app.models.order", "Order"),
    ("app.models.order_item", "OrderItem"),
    ("app.models.order_line", "OrderLine"),
    ("app.models.order_logistics", "OrderLogistics"),
    ("app.models.order_state_snapshot", "OrderStateSnapshot"),
    ("app.models.order_shipment_prepare", "OrderShipmentPrepare"),
    ("app.models.order_shipment_prepare_package", "OrderShipmentPreparePackage"),
    # ✅ Phase 5：执行域 authority（order_fulfillment）
    ("app.models.order_fulfillment", "OrderFulfillment"),
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
    # 门店 & 权限导航
    # ------------------------------------------------------------------
    ("app.models.store", "Store"),
    ("app.models.user", "User"),
    ("app.models.permission", "Permission"),
    ("app.models.page_registry", "PageRegistry"),
    ("app.models.page_route_prefix", "PageRoutePrefix"),
    # ------------------------------------------------------------------
    # 店铺 × 平台接入（OMS 淘宝 / 拼多多 / 京东）
    # ------------------------------------------------------------------
    ("app.models.taobao_app_config", "TaobaoAppConfig"),
    ("app.models.pdd_app_config", "PddAppConfig"),
    ("app.models.jd_app_config", "JdAppConfig"),
    ("app.models.store_platform_credential", "StorePlatformCredential"),
    ("app.models.store_platform_connection", "StorePlatformConnection"),
    ("app.models.taobao_order", "TaobaoOrder"),
    ("app.models.taobao_order", "TaobaoOrderItem"),
    ("app.models.pdd_order", "PddOrder"),
    ("app.models.pdd_order", "PddOrderItem"),
    ("app.models.jd_order", "JdOrder"),
    ("app.models.jd_order", "JdOrderItem"),
    ("app.models.pdd_order_order_mapping", "PddOrderOrderMapping"),
    # ------------------------------------------------------------------
    # 采购系统
    # ------------------------------------------------------------------
    ("app.procurement.models.purchase_order", "PurchaseOrder"),
    ("app.procurement.models.purchase_order_line", "PurchaseOrderLine"),
    # ------------------------------------------------------------------
    # 收货事实（兼容期保留，待旧主线退役）
    # ------------------------------------------------------------------
    ("app.procurement.models.inbound_receipt", "InboundReceipt"),
    ("app.procurement.models.inbound_receipt", "InboundReceiptLine"),
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
    # 运输执行 / 账本（Phase-2：Shipment 主实体 + Record 投影）
    # ------------------------------------------------------------------
    ("app.models.transport_shipment", "TransportShipment"),
    ("app.models.shipping_record", "ShippingRecord"),
    ("app.models.carrier_bill_item", "CarrierBillItem"),
    ("app.models.shipping_record_reconciliation", "ShippingRecordReconciliation"),
    # ------------------------------------------------------------------
    # 运价模板（新主线：template -> ranges/groups -> matrix + surcharge_config）
    # ------------------------------------------------------------------
    (
        "app.models.shipping_provider_pricing_template_surcharge_config_city",
        "ShippingProviderPricingTemplateSurchargeConfigCity",
    ),
    (
        "app.models.shipping_provider_pricing_template_surcharge_config",
        "ShippingProviderPricingTemplateSurchargeConfig",
    ),
    ("app.models.shipping_provider_pricing_template", "ShippingProviderPricingTemplate"),
    (
        "app.models.shipping_provider_pricing_template_validation_record",
        "ShippingProviderPricingTemplateValidationRecord",
    ),
    (
        "app.models.shipping_provider_pricing_template_module_range",
        "ShippingProviderPricingTemplateModuleRange",
    ),
    (
        "app.models.shipping_provider_pricing_template_destination_group",
        "ShippingProviderPricingTemplateDestinationGroup",
    ),
    (
        "app.models.shipping_provider_pricing_template_destination_group_member",
        "ShippingProviderPricingTemplateDestinationGroupMember",
    ),
    ("app.models.shipping_provider_pricing_template_matrix", "ShippingProviderPricingTemplateMatrix"),
    # ------------------------------------------------------------------
    # 运价实例（终态主线：scheme -> ranges/groups -> pricing_matrix + surcharge_config）
    # ------------------------------------------------------------------
]


# 实际导出
for _module, _name in MODEL_SPECS:
    _export(_module, _name)

__all__ = [
    # ---- Master Data ----
    "Supplier",
    "SupplierContact",
    "WarehouseShippingProvider",
    "ShippingProvider",
    "ShippingProviderContact",
    "ElectronicWaybillConfig",
    # ---- Inventory ----
    "Warehouse",
    "Item",
    "ItemUOM",
    "ItemTestSet",
    "ItemTestSetItem",
    "Lot",
    "StockLot",
    "StockLedger",
    "StockSnapshot",
    "WmsEvent",
    "InboundEventLine",
    # ---- Orders ----
    "Order",
    "OrderItem",
    "OrderLine",
    "OrderLogistics",
    "OrderStateSnapshot",
    "OrderShipmentPrepare",
    "OrderShipmentPreparePackage",
    "OrderFulfillment",
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
    # ---- Store & Access ----
    "Store",
    "User",
    "Permission",
    "PageRegistry",
    "PageRoutePrefix",
    # ---- Store Platform Access ----
    "TaobaoAppConfig",
    "PddAppConfig",
    "JdAppConfig",
    "StorePlatformCredential",
    "StorePlatformConnection",
    "TaobaoOrder",
    "TaobaoOrderItem",
    "PddOrder",
    "PddOrderItem",
    "JdOrder",
    "JdOrderItem",
    "PddOrderOrderMapping",
    # ---- Purchase ----
    "PurchaseOrder",
    "PurchaseOrderLine",
    # ---- Inbound (legacy receipt compatibility) ----
    "InboundReceipt",
    "InboundReceiptLine",
    # ---- Return ----
    "ReturnTask",
    "ReturnTaskLine",
    # ---- Internal Outbound ----
    "InternalOutboundDoc",
    "InternalOutboundLine",
    # ---- Shipping ----
    "TransportShipment",
    "ShippingRecord",
    "CarrierBillItem",
    "ShippingRecordReconciliation",
    "ShippingProviderPricingTemplateSurchargeConfigCity",
    "ShippingProviderPricingTemplateSurchargeConfig",
    "ShippingProviderPricingTemplate",
    "ShippingProviderPricingTemplateValidationRecord",
    "ShippingProviderPricingTemplateModuleRange",
    "ShippingProviderPricingTemplateDestinationGroup",
    "ShippingProviderPricingTemplateDestinationGroupMember",
    "ShippingProviderPricingTemplateMatrix",
]
