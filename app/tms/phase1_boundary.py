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
    - 当前已进入后端 router 壳物理归位阶段，因此规则同时覆盖：
      1) 历史叶子 route 文件；
      2) 新的 TMS router 壳文件。
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
        description="shipping_record 是运输事实台帐，由 TMS/TransportLedger 主拥有。",
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
        path_prefix="app/tms/providers/",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_CONFIG,
        note="TMS / providers 子域。",
    ),
    FileOwnershipRule(
        path_prefix="app/tms/pricing/",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_CONFIG,
        note="TMS / pricing 子域。",
    ),
    FileOwnershipRule(
        path_prefix="app/tms/quote/router.py",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_QUOTE,
        note="Quote 新主路由壳。",
    ),
    FileOwnershipRule(
        path_prefix="app/tms/quote/",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_QUOTE,
        note="Quote 主模块。",
    ),
    FileOwnershipRule(
        path_prefix="app/tms/quote_snapshot/",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_QUOTE,
        note="QuoteSnapshot 主合同与构建/校验逻辑，由 Quote 域主拥有。",
    ),
    FileOwnershipRule(
        path_prefix="app/tms/alerts/",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_QUOTE,
        note="告警聚合服务；当前承载 SHIPPING_QUOTE 告警与历史运输异常观测。",
    ),
    FileOwnershipRule(
        path_prefix="app/tms/shipment/waybill_service.py",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_SHIPMENT,
        note="Shipment 面单申请服务实现。",
    ),
    FileOwnershipRule(
        path_prefix="app/tms/shipment/orders_v2_router.py",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_SHIPMENT,
        note="Shipment 在 orders_fulfillment_v2 下的新主路由壳。",
    ),
    FileOwnershipRule(
        path_prefix="app/tms/shipment/contracts_calc.py",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_SHIPMENT,
        note="Shipment /ship/calc 合同定义。",
    ),
    FileOwnershipRule(
        path_prefix="app/tms/shipment/contracts_prepare.py",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_SHIPMENT,
        note="Shipment /ship/prepare-from-order 合同定义。",
    ),
    FileOwnershipRule(
        path_prefix="app/tms/shipment/router.py",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_SHIPMENT,
        note="Shipment 在 /ship 下的新主路由壳。",
    ),
    FileOwnershipRule(
        path_prefix="app/tms/shipment/routes_calc.py",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_SHIPMENT,
        note="Shipment /ship/calc 路由实现。",
    ),
    FileOwnershipRule(
        path_prefix="app/tms/shipment/routes_prepare.py",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_SHIPMENT,
        note="Shipment /ship/prepare-from-order 路由实现。",
    ),
    FileOwnershipRule(
        path_prefix="app/tms/shipment/routes_ship_with_waybill.py",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_SHIPMENT,
        note="Shipment /orders/.../ship-with-waybill 路由实现。",
    ),
    FileOwnershipRule(
        path_prefix="app/tms/shipment/api_contracts.py",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_SHIPMENT,
        note="Shipment API 合同定义（含 ShipWithWaybill 请求/响应）。",
    ),
    FileOwnershipRule(
        path_prefix="app/tms/shipment/",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_SHIPMENT,
        note="Shipment 主模块。",
    ),
    FileOwnershipRule(
        path_prefix="app/api/routers/orders_fulfillment_v2_schemas.py",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_SHIPMENT,
        note="历史共享 schema 文件；当前仅保留 Pick 合同。",
    ),
    FileOwnershipRule(
        path_prefix="app/api/routers/outbound_ship_routes_confirm.py",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_SHIPMENT,
        note="当前挂在 Outbound，但语义属于 Shipment；已由 TMS router 壳统一挂载。",
    ),
    FileOwnershipRule(
        path_prefix="app/models/shipping_record.py",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_LEDGER,
        note="运输账本事实模型。",
    ),
    FileOwnershipRule(
        path_prefix="app/tms/records/router.py",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_LEDGER,
        note="Records 新主路由装配入口。",
    ),
    FileOwnershipRule(
        path_prefix="app/tms/records/contracts.py",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_LEDGER,
        note="Records 账本只读合同。",
    ),
    FileOwnershipRule(
        path_prefix="app/tms/records/repository.py",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_LEDGER,
        note="Records 账本只读查询实现。",
    ),
    FileOwnershipRule(
        path_prefix="app/tms/records/routes_read.py",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_LEDGER,
        note="Records 账本读取路由。",
    ),
    FileOwnershipRule(
        path_prefix="app/api/routers/shipping_reports_routes_",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_REPORTS,
        note="历史运输报表叶子路由；冻结归属仍属于 TransportReports。",
    ),
    FileOwnershipRule(
        path_prefix="app/tms/reports/router.py",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_REPORTS,
        note="Reports 新主路由壳。",
    ),
    FileOwnershipRule(
        path_prefix="app/tms/reports/routes_",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_REPORTS,
        note="运输报表子路由实现。",
    ),
    FileOwnershipRule(
        path_prefix="app/tms/reports/helpers.py",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_REPORTS,
        note="运输报表 helper。",
    ),
    FileOwnershipRule(
        path_prefix="app/tms/reports/contracts.py",
        owner_domain=DomainOwner.TMS,
        owner_subdomain=TmsSubdomain.TRANSPORT_REPORTS,
        note="运输报表合同定义。",
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
