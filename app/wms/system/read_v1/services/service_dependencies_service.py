# app/wms/system/read_v1/services/service_dependencies_service.py
from __future__ import annotations

from dataclasses import dataclass

from app.wms.system.read_v1.contracts import (
    WmsSystemServiceDependenciesOut,
    WmsSystemServiceDependencyEndpointOut,
    WmsSystemServiceDependencyOut,
)

WMS_APP_CODE = "wms"
WMS_APP_NAME = "仓储管理"
WMS_SERVICE_CLIENT_CODE = "wms-service"


@dataclass(frozen=True)
class ServiceDependencyEndpoint:
    http_method: str
    path: str
    purpose: str | None = None


@dataclass(frozen=True)
class ServiceDependency:
    dependency_code: str
    dependency_name: str
    target_app_code: str
    target_capability_code: str
    description: str
    is_required: bool
    is_active: bool
    required_config_keys: tuple[str, ...]
    source_modules: tuple[str, ...]
    endpoints: tuple[ServiceDependencyEndpoint, ...]


WMS_SERVICE_DEPENDENCIES: tuple[ServiceDependency, ...] = (
    ServiceDependency(
        dependency_code="wms.depends_on.pms.projection_feed",
        dependency_name="PMS projection feed",
        target_app_code="pms",
        target_capability_code="pms.read.projection_feed",
        description="WMS 同步 PMS 当前态只读投影，用于商品、供应商、包装单位、SKU 编码与条码查询。",
        is_required=True,
        is_active=True,
        required_config_keys=("PMS_API_BASE_URL",),
        source_modules=(
            "app.integrations.pms.projection_sync",
            "scripts.pms.sync_projection",
        ),
        endpoints=(
            ServiceDependencyEndpoint(
                http_method="GET",
                path="/pms/read/v1/projection-feed/items",
                purpose="同步 PMS 商品投影。",
            ),
            ServiceDependencyEndpoint(
                http_method="GET",
                path="/pms/read/v1/projection-feed/suppliers",
                purpose="同步 PMS 供应商投影。",
            ),
            ServiceDependencyEndpoint(
                http_method="GET",
                path="/pms/read/v1/projection-feed/uoms",
                purpose="同步 PMS 包装单位投影。",
            ),
            ServiceDependencyEndpoint(
                http_method="GET",
                path="/pms/read/v1/projection-feed/sku-codes",
                purpose="同步 PMS SKU 编码投影。",
            ),
            ServiceDependencyEndpoint(
                http_method="GET",
                path="/pms/read/v1/projection-feed/barcodes",
                purpose="同步 PMS 条码投影。",
            ),
        ),
    ),
    ServiceDependency(
        dependency_code="wms.depends_on.pms.item_read",
        dependency_name="PMS item read",
        target_app_code="pms",
        target_capability_code="pms.read.items",
        description="WMS 通过 PMS read-v1 读取商品基础信息、商品策略与报表元数据。",
        is_required=True,
        is_active=True,
        required_config_keys=("PMS_API_BASE_URL",),
        source_modules=("app.integrations.pms.http_client",),
        endpoints=(
            ServiceDependencyEndpoint(
                http_method="GET",
                path="/pms/read/v1/items/basic",
                purpose="读取商品基础列表。",
            ),
            ServiceDependencyEndpoint(
                http_method="POST",
                path="/pms/read/v1/items/basic/batch",
                purpose="批量读取商品基础信息。",
            ),
            ServiceDependencyEndpoint(
                http_method="POST",
                path="/pms/read/v1/items/policies/batch",
                purpose="批量读取商品策略。",
            ),
            ServiceDependencyEndpoint(
                http_method="GET",
                path="/pms/read/v1/items/policy-by-sku",
                purpose="按 SKU 读取商品策略。",
            ),
            ServiceDependencyEndpoint(
                http_method="GET",
                path="/pms/read/v1/items/report-search",
                purpose="按关键字搜索报表商品 ID。",
            ),
            ServiceDependencyEndpoint(
                http_method="POST",
                path="/pms/read/v1/items/report-meta/batch",
                purpose="批量读取报表商品元数据。",
            ),
        ),
    ),
    ServiceDependency(
        dependency_code="wms.depends_on.pms.uom_read",
        dependency_name="PMS UOM read",
        target_app_code="pms",
        target_capability_code="pms.read.uoms",
        description="WMS 通过 PMS read-v1 读取包装单位及默认单位。",
        is_required=True,
        is_active=True,
        required_config_keys=("PMS_API_BASE_URL",),
        source_modules=("app.integrations.pms.http_client",),
        endpoints=(
            ServiceDependencyEndpoint(
                http_method="POST",
                path="/pms/read/v1/uoms/query",
                purpose="查询包装单位。",
            ),
            ServiceDependencyEndpoint(
                http_method="POST",
                path="/pms/read/v1/items/uom-defaults/batch",
                purpose="批量读取商品默认包装单位。",
            ),
        ),
    ),
    ServiceDependency(
        dependency_code="wms.depends_on.pms.barcode_read",
        dependency_name="PMS barcode read",
        target_app_code="pms",
        target_capability_code="pms.read.barcodes",
        description="WMS 通过 PMS read-v1 读取、查询与探测条码。",
        is_required=True,
        is_active=True,
        required_config_keys=("PMS_API_BASE_URL",),
        source_modules=("app.integrations.pms.http_client",),
        endpoints=(
            ServiceDependencyEndpoint(
                http_method="GET",
                path="/pms/read/v1/barcodes/{barcode_id}",
                purpose="按 ID 读取条码。",
            ),
            ServiceDependencyEndpoint(
                http_method="POST",
                path="/pms/read/v1/barcodes/query",
                purpose="查询条码。",
            ),
            ServiceDependencyEndpoint(
                http_method="POST",
                path="/pms/read/v1/barcodes/probe",
                purpose="条码探测。",
            ),
        ),
    ),
    ServiceDependency(
        dependency_code="wms.depends_on.pms.sku_code_read",
        dependency_name="PMS SKU code read",
        target_app_code="pms",
        target_capability_code="pms.read.sku_codes",
        description="WMS 通过 PMS read-v1 读取 SKU 编码并解析出库默认编码。",
        is_required=True,
        is_active=True,
        required_config_keys=("PMS_API_BASE_URL",),
        source_modules=(
            "app.integrations.pms.http_client",
            "app.integrations.pms.sync_http_client",
        ),
        endpoints=(
            ServiceDependencyEndpoint(
                http_method="POST",
                path="/pms/read/v1/sku-codes/query",
                purpose="查询 SKU 编码。",
            ),
            ServiceDependencyEndpoint(
                http_method="GET",
                path="/pms/read/v1/sku-codes/resolve-outbound-default",
                purpose="解析出库默认 SKU 编码。",
            ),
        ),
    ),
    ServiceDependency(
        dependency_code="wms.depends_on.oms.fulfillment_ready_orders",
        dependency_name="OMS fulfillment-ready orders",
        target_app_code="oms",
        target_capability_code="oms.read.fulfillment_ready_orders",
        description="WMS 从 OMS 读取可履约订单，用于出库侧 OMS 履约投影同步。",
        is_required=True,
        is_active=True,
        required_config_keys=("OMS_API_BASE_URL",),
        source_modules=(
            "app.integrations.oms.projection_sync",
            "scripts.oms.sync_fulfillment_projection",
        ),
        endpoints=(
            ServiceDependencyEndpoint(
                http_method="GET",
                path="/oms/read/v1/fulfillment-ready-orders",
                purpose="读取 OMS 可履约订单列表。",
            ),
        ),
    ),
    ServiceDependency(
        dependency_code="wms.depends_on.procurement.receiving_sources",
        dependency_name="Procurement receiving sources",
        target_app_code="procurement",
        target_capability_code="procurement.read.wms_receiving_sources",
        description="WMS 从 Procurement 读取采购入库来源，用于采购收货。",
        is_required=True,
        is_active=True,
        required_config_keys=("PROCUREMENT_API_BASE_URL",),
        source_modules=("app.integrations.procurement.http_client",),
        endpoints=(
            ServiceDependencyEndpoint(
                http_method="GET",
                path="/procurement/read/v1/wms/receiving-sources",
                purpose="读取采购入库来源选项。",
            ),
            ServiceDependencyEndpoint(
                http_method="GET",
                path="/procurement/read/v1/wms/receiving-sources/{po_id}",
                purpose="读取采购入库来源详情。",
            ),
        ),
    ),
    ServiceDependency(
        dependency_code="wms.depends_on.logistics.shipping_record_facts",
        dependency_name="Logistics shipping record facts",
        target_app_code="logistics",
        target_capability_code="logistics.read.shipping_record_facts",
        description="WMS 从 Logistics 同步发货记录事实，用于 WMS 发货记录投影。",
        is_required=True,
        is_active=True,
        required_config_keys=(
            "LOGISTICS_API_BASE_URL",
            "LOGISTICS_API_TOKEN",
            "LOGISTICS_API_TIMEOUT_SECONDS",
        ),
        source_modules=(
            "app.shipping_assist.records.sync.client",
            "app.shipping_assist.records.sync.service",
            "scripts.sync_logistics_shipping_records",
        ),
        endpoints=(
            ServiceDependencyEndpoint(
                http_method="GET",
                path="/logistics/read/v1/shipping-record-facts",
                purpose="读取 Logistics 发货记录事实。",
            ),
        ),
    ),
)


def _endpoint_out(endpoint: ServiceDependencyEndpoint) -> WmsSystemServiceDependencyEndpointOut:
    return WmsSystemServiceDependencyEndpointOut(
        http_method=endpoint.http_method,
        path=endpoint.path,
        purpose=endpoint.purpose,
    )


def _dependency_out(dependency: ServiceDependency) -> WmsSystemServiceDependencyOut:
    return WmsSystemServiceDependencyOut(
        dependency_code=dependency.dependency_code,
        dependency_name=dependency.dependency_name,
        target_app_code=dependency.target_app_code,
        target_capability_code=dependency.target_capability_code,
        required_permission_code=dependency.target_capability_code,
        description=dependency.description,
        is_required=dependency.is_required,
        is_active=dependency.is_active,
        required_config_keys=list(dependency.required_config_keys),
        source_modules=list(dependency.source_modules),
        endpoints=[_endpoint_out(endpoint) for endpoint in dependency.endpoints],
    )


def build_wms_service_dependencies() -> WmsSystemServiceDependenciesOut:
    """
    Return WMS declared outbound service dependencies.

    Boundary:
    - This is only a declaration of what WMS needs.
    - It is not ERP approval.
    - It is not a grant.
    - It is not a write-back result.
    - It is not runtime verification.
    """

    return WmsSystemServiceDependenciesOut(
        app_code=WMS_APP_CODE,
        app_name=WMS_APP_NAME,
        source_service_client_code=WMS_SERVICE_CLIENT_CODE,
        dependencies=[_dependency_out(row) for row in WMS_SERVICE_DEPENDENCIES],
    )


__all__ = [
    "WMS_APP_CODE",
    "WMS_APP_NAME",
    "WMS_SERVICE_CLIENT_CODE",
    "WMS_SERVICE_DEPENDENCIES",
    "ServiceDependency",
    "ServiceDependencyEndpoint",
    "build_wms_service_dependencies",
]
