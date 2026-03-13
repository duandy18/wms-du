# app/tms/phase1_boundary.py
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath


class DomainOwner(StrEnum):
    TMS = "TMS"
    WMS = "WMS"
    OMS = "OMS"


class TmsSubdomain(StrEnum):
    TRANSPORT_CONFIG = "TransportConfig"
    TRANSPORT_QUOTE = "TransportQuote"
    TRANSPORT_SHIPMENT = "TransportShipment"
    TRANSPORT_LEDGER = "TransportLedger"
    TRANSPORT_REPORTS = "TransportReports"


@dataclass(frozen=True, slots=True)
class FrozenOwnership:
    """
    第一阶段冻结后的对象所有权定义。

    code:
        对象/能力代号，供代码、测试、后续文档统一引用。
    owner_domain:
        一级领域所有者（TMS / WMS / OMS）。
    owner_subdomain:
        若 owner_domain = TMS，则进一步指向 TMS 子域。
        非 TMS 对象可为 None。
    collaborators:
        协作域列表；不代表拥有权。
    description:
        对该对象/能力的冻结定义。
    """

    code: str
    owner_domain: DomainOwner
    owner_subdomain: TmsSubdomain | None
    collaborators: tuple[DomainOwner, ...]
    description: str


@dataclass(frozen=True, slots=True)
class FileOwnershipRule:
    """
    当前仓库物理文件归属冻结规则。

    说明：
    - Phase 1 先冻结语义归属，不要求立刻物理迁目录。
    - 允许“当前挂在旧目录，但领域归属已改判为 TMS”。
    """

    path_prefix: str
    owner_domain: DomainOwner
    owner_subdomain: TmsSubdomain | None
    note: str


FROZEN_OWNERSHIP: dict[str, FrozenOwnership] = {
    "shipping_provider": FrozenOwnership(
        code="shipping_provider",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_CONFIG,
        collaborators=(DomainOwner.WMS,),
        description="运输网点实体，由 TMS/TransportConfig 主拥有。",
    ),
    "warehouse_shipping_provider_binding": FrozenOwnership(
        code="warehouse_shipping_provider_binding",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_CONFIG,
        collaborators=(DomainOwner.WMS,),
        description="仓库与运输网点绑定属于运输配置，不属于 WMS 私有配置。",
    ),
    "pricing_scheme": FrozenOwnership(
        code="pricing_scheme",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_CONFIG,
        collaborators=(DomainOwner.WMS,),
        description="运价方案由 TMS/TransportConfig 主拥有。",
    ),
    "destination_group": FrozenOwnership(
        code="destination_group",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_CONFIG,
        collaborators=(DomainOwner.TMS,),
        description="区域规则属于 TMS/TransportConfig。",
    ),
    "pricing_matrix": FrozenOwnership(
        code="pricing_matrix",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_CONFIG,
        collaborators=(DomainOwner.TMS,),
        description="价格矩阵属于 TMS/TransportConfig。",
    ),
    "surcharge_config": FrozenOwnership(
        code="surcharge_config",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_CONFIG,
        collaborators=(DomainOwner.TMS,),
        description="附加费配置属于 TMS/TransportConfig。",
    ),
    "quote": FrozenOwnership(
        code="quote",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_QUOTE,
        collaborators=(DomainOwner.WMS, DomainOwner.OMS),
        description="运费计算与推荐属于 TMS/TransportQuote。",
    ),
    "quote_snapshot": FrozenOwnership(
        code="quote_snapshot",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_QUOTE,
        collaborators=(DomainOwner.WMS, DomainOwner.OMS),
        description="QuoteSnapshot 由 Quote 产出，被 Shipment 消费，是执行证据包。",
    ),
    "shipment_execution": FrozenOwnership(
        code="shipment_execution",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_SHIPMENT,
        collaborators=(DomainOwner.WMS, DomainOwner.OMS),
        description="Shipment 执行属于 TMS/TransportShipment。",
    ),
    "waybill_request": FrozenOwnership(
        code="waybill_request",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_SHIPMENT,
        collaborators=(DomainOwner.OMS,),
        description="面单申请属于 TMS/TransportShipment。",
    ),
    "tracking_number": FrozenOwnership(
        code="tracking_number",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_SHIPMENT,
        collaborators=(DomainOwner.WMS, DomainOwner.OMS),
        description="运单号属于 Shipment 执行事实。",
    ),
    "shipping_record_write": FrozenOwnership(
        code="shipping_record_write",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_SHIPMENT,
        collaborators=(DomainOwner.TMS,),
        description="shipping_record 的 create/upsert 入口由 Shipment 主拥有，必须统一收口。",
    ),
    "shipping_record": FrozenOwnership(
        code="shipping_record",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_LEDGER,
        collaborators=(DomainOwner.WMS, DomainOwner.OMS),
        description="shipping_record 是 Shipment 的账本事实投影，由 TMS/TransportLedger 主拥有。",
    ),
    "shipping_report": FrozenOwnership(
        code="shipping_report",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_REPORTS,
        collaborators=(DomainOwner.WMS,),
        description="运输统计统一属于 TMS/TransportReports。",
    ),
    "order": FrozenOwnership(
        code="order",
        owner_domain=DomainOwner.OMS,
        owner_subdomain=None,
        collaborators=(DomainOwner.TMS, DomainOwner.WMS),
        description="Order 是业务来源对象，不是运输域核心对象。",
    ),
    "warehouse_outbound": FrozenOwnership(
        code="warehouse_outbound",
        owner_domain=DomainOwner.WMS,
        owner_subdomain=None,
        collaborators=(DomainOwner.TMS,),
        description="仓内出库属于 WMS；可触发 Shipment，但不拥有运输执行主线。",
    ),
}


FILE_OWNERSHIP_RULES: tuple[FileOwnershipRule, ...] = (
    FileOwnershipRule(
        path_prefix="app/models/shipping_provider.py",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_CONFIG,
        note="运输网点实体。",
    ),
    FileOwnershipRule(
        path_prefix="app/models/warehouse_shipping_provider.py",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_CONFIG,
        note="仓库-运输网点绑定。",
    ),
    FileOwnershipRule(
        path_prefix="app/models/shipping_provider_contact.py",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_CONFIG,
        note="运输联系人配置。",
    ),
    FileOwnershipRule(
        path_prefix="app/models/shipping_provider_pricing_scheme.py",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_CONFIG,
        note="运价方案主模型。",
    ),
    FileOwnershipRule(
        path_prefix="app/models/shipping_provider_pricing_scheme_module_range.py",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_CONFIG,
        note="重量段模块。",
    ),
    FileOwnershipRule(
        path_prefix="app/models/shipping_provider_destination_group.py",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_CONFIG,
        note="区域组主模型。",
    ),
    FileOwnershipRule(
        path_prefix="app/models/shipping_provider_destination_group_member.py",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_CONFIG,
        note="区域组成员。",
    ),
    FileOwnershipRule(
        path_prefix="app/models/shipping_provider_pricing_matrix.py",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_CONFIG,
        note="价格矩阵主模型。",
    ),
    FileOwnershipRule(
        path_prefix="app/models/shipping_provider_surcharge_config.py",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_CONFIG,
        note="附加费主模型。",
    ),
    FileOwnershipRule(
        path_prefix="app/models/shipping_provider_surcharge_config_city.py",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_CONFIG,
        note="附加费城市子模型。",
    ),
    FileOwnershipRule(
        path_prefix="app/services/shipping_quote/",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_QUOTE,
        note="Quote 服务簇。",
    ),
    FileOwnershipRule(
        path_prefix="app/services/shipping_quote_service.py",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_QUOTE,
        note="Quote 兼容导出层。",
    ),
    FileOwnershipRule(
        path_prefix="app/api/routers/shipping_quote",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_QUOTE,
        note="Quote 路由。",
    ),
    FileOwnershipRule(
        path_prefix="app/tms/quote_snapshot/",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_QUOTE,
        note="QuoteSnapshot 主合同与构建/校验逻辑，由 Quote 域主拥有。",
    ),
    FileOwnershipRule(
        path_prefix="app/services/waybill_service.py",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_SHIPMENT,
        note="面单申请服务。",
    ),
    FileOwnershipRule(
        path_prefix="app/api/routers/orders_fulfillment_v2_routes_4_ship_with_waybill.py",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_SHIPMENT,
        note="当前挂在 Fulfillment，但语义属于 Shipment。",
    ),
    FileOwnershipRule(
        path_prefix="app/api/routers/orders_fulfillment_v2_helpers.py",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_SHIPMENT,
        note="当前仍是兼容转发层；其中 quote_snapshot 相关逻辑已改为消费 Quote 域合同。",
    ),
    FileOwnershipRule(
        path_prefix="app/api/routers/orders_fulfillment_v2_schemas.py",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_SHIPMENT,
        note="其中 ShipWithWaybill 合同语义属于 Shipment。",
    ),
    FileOwnershipRule(
        path_prefix="app/api/routers/outbound_ship_routes_confirm.py",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_SHIPMENT,
        note="当前挂在 Outbound，但语义属于 Shipment；属于待收口旧入口。",
    ),
    FileOwnershipRule(
        path_prefix="app/api/routers/outbound_ship_schemas.py",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_SHIPMENT,
        note="其中 ShipConfirm 合同语义属于 Shipment。",
    ),
    FileOwnershipRule(
        path_prefix="app/models/shipping_record.py",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_LEDGER,
        note="运输账本事实模型。",
    ),
    FileOwnershipRule(
        path_prefix="app/api/routers/shipping_records.py",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_LEDGER,
        note="账本查询与状态入口。",
    ),
    FileOwnershipRule(
        path_prefix="app/api/routers/shipping_records_routes_read.py",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_LEDGER,
        note="账本读取入口。",
    ),
    FileOwnershipRule(
        path_prefix="app/api/routers/shipping_records_routes_status.py",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_LEDGER,
        note="账本状态推进入口。",
    ),
    FileOwnershipRule(
        path_prefix="app/jobs/shipping_delivery_sync_apply.py",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_LEDGER,
        note="平台状态回写账本。",
    ),
    FileOwnershipRule(
        path_prefix="app/jobs/shipping_delivery_sync_runner.py",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_LEDGER,
        note="平台状态同步 runner。",
    ),
    FileOwnershipRule(
        path_prefix="app/api/routers/shipping_reports.py",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_REPORTS,
        note="运输报表总路由。",
    ),
    FileOwnershipRule(
        path_prefix="app/api/routers/shipping_reports_routes_",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_REPORTS,
        note="运输报表子路由。",
    ),
    FileOwnershipRule(
        path_prefix="app/api/routers/shipping_reports_helpers.py",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_REPORTS,
        note="运输报表 helper。",
    ),
)


def get_frozen_ownership(code: str) -> FrozenOwnership:
    """
    返回第一阶段冻结对象的所有权定义。

    Raises:
        KeyError: 当 code 不存在时抛出。
    """
    return FROZEN_OWNERSHIP[code]


def find_file_ownership(path: str) -> FileOwnershipRule | None:
    """
    根据文件路径返回冻结后的领域归属。

    规则：
    - 采用前缀匹配
    - 更长的 path_prefix 优先，避免上层前缀吞掉更具体规则
    """
    normalized = PurePosixPath(path).as_posix()
    matched: FileOwnershipRule | None = None

    for rule in sorted(FILE_OWNERSHIP_RULES, key=lambda item: len(item.path_prefix), reverse=True):
        if normalized.startswith(rule.path_prefix):
            matched = rule
            break

    return matched
