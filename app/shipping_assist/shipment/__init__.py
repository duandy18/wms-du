# app/shipping_assist/shipment/__init__.py
"""
TMS / TransportShipment module.

当前终态：
- /ship-with-waybill 是 Shipment Execution 唯一主入口；
- shipping_records 的 create/upsert 写入口统一由 TransportShipment 控制；
- QuoteSnapshot 主合同归属 app.shipping_assist.quote_snapshot，由 Shipment 消费；
- 平台状态不再回写运输账本，不再提供本地状态写能力。
"""

from app.shipping_assist.quote_snapshot import (
    extract_cost_estimated,
    extract_quote_snapshot,
    validate_quote_snapshot,
)

from .contracts import (
    ShipmentApplicationError,
    ShipCommitAuditCommand,
    ShipCommitAuditResult,
    ShipWithWaybillCommand,
    ShipWithWaybillResult,
)
from .service import TransportShipmentService

__all__ = [
    "ShipmentApplicationError",
    "ShipCommitAuditCommand",
    "ShipCommitAuditResult",
    "ShipWithWaybillCommand",
    "ShipWithWaybillResult",
    "extract_cost_estimated",
    "extract_quote_snapshot",
    "validate_quote_snapshot",
    "TransportShipmentService",
]
