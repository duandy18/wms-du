# app/tms/shipment/contracts_prepare.py
# 分拆说明：
# - 本文件已从“大而全 prepare 合同文件”收口为薄壳聚合入口。
# - 当前只负责兼容导出：
#   1) 订单与地址 contracts_prepare_orders
#   2) 包裹基础事实 contracts_prepare_packages
#   3) 包裹报价 contracts_prepare_quotes
# - 维护约束：
#   - 不在本文件继续新增具体合同定义
#   - 新增 prepare 合同时优先落到对应功能子文件
from __future__ import annotations

from .contracts_prepare_orders import (
    ShipPrepareAddressConfirmRequest,
    ShipPrepareAddressConfirmResponse,
    ShipPrepareImportRequest,
    ShipPrepareImportResponse,
    ShipPrepareOrderDetailOut,
    ShipPrepareOrderDetailResponse,
    ShipPrepareOrdersListItemOut,
    ShipPrepareOrdersListResponse,
)
from .contracts_prepare_packages import (
    ShipPreparePackageCreateResponse,
    ShipPreparePackageOut,
    ShipPreparePackagesResponse,
    ShipPreparePackageUpdateRequest,
    ShipPreparePackageUpdateResponse,
)
from .contracts_prepare_quotes import (
    ShipPreparePackageQuoteConfirmOut,
    ShipPreparePackageQuoteConfirmRequest,
    ShipPreparePackageQuoteConfirmResponse,
    ShipPreparePackageQuoteOut,
    ShipPreparePackageQuoteResponse,
    ShipPrepareQuoteCandidateOut,
)

__all__ = [
    "ShipPrepareImportRequest",
    "ShipPrepareImportResponse",
    "ShipPrepareOrdersListItemOut",
    "ShipPrepareOrdersListResponse",
    "ShipPrepareOrderDetailOut",
    "ShipPrepareOrderDetailResponse",
    "ShipPrepareAddressConfirmRequest",
    "ShipPrepareAddressConfirmResponse",
    "ShipPreparePackageOut",
    "ShipPreparePackagesResponse",
    "ShipPreparePackageCreateResponse",
    "ShipPreparePackageUpdateRequest",
    "ShipPreparePackageUpdateResponse",
    "ShipPrepareQuoteCandidateOut",
    "ShipPreparePackageQuoteOut",
    "ShipPreparePackageQuoteResponse",
    "ShipPreparePackageQuoteConfirmRequest",
    "ShipPreparePackageQuoteConfirmOut",
    "ShipPreparePackageQuoteConfirmResponse",
]
