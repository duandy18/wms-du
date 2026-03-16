# app/tms/shipment/__init__.py
"""
TMS / TransportShipment module.

当前终态：
- /ship-with-waybill 是 Shipment Execution 唯一主入口；
- shipping_records 的 create/upsert 写入口统一由 TransportShipment 控制；
- QuoteSnapshot 主合同归属 app.tms.quote_snapshot，由 Shipment 消费；
- 本地物流状态真相与双写同步路线已废止，不再作为 Shipment 主能力。
"""

from app.tms.quote_snapshot import (
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
    UpdateShipmentStatusCommand,
    UpdateShipmentStatusResult,
)
from .service import TransportShipmentService

__all__ = [
    "ShipmentApplicationError",
    "ShipCommitAuditCommand",
    "ShipCommitAuditResult",
    "ShipWithWaybillCommand",
    "ShipWithWaybillResult",
    "UpdateShipmentStatusCommand",
    "UpdateShipmentStatusResult",
    "extract_cost_estimated",
    "extract_quote_snapshot",
    "validate_quote_snapshot",
    "TransportShipmentService",
]
