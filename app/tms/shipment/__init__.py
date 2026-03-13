# app/tms/shipment/__init__.py
"""
TMS / TransportShipment module shell.

Phase 2 终态目标：
- ship_with_waybill 成为 Shipment 唯一主写入口
- Shipment 主真相落在 transport_shipments
- shipping_records 降级为 projection / ledger
- status 更新必须同步主实体与 projection
"""

from .contracts import (
    ShipmentApplicationError,
    ShipCommitAuditCommand,
    ShipCommitAuditResult,
    ShipWithWaybillCommand,
    ShipWithWaybillResult,
    UpdateShipmentStatusCommand,
    UpdateShipmentStatusResult,
)
from .quote_snapshot import (
    extract_cost_estimated,
    extract_quote_snapshot,
    validate_quote_snapshot,
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
