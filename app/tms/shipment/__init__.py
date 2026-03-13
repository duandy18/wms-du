# app/tms/shipment/__init__.py
"""
TMS / TransportShipment module shell.

Phase 1 目标：
- 收口 Shipment 执行主逻辑
- 统一 shipping_record 写入口
- 为后续 route / file physical migration 做准备
"""

from .contracts import (
    ConfirmShipmentCommand,
    ConfirmShipmentResult,
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
    "ConfirmShipmentCommand",
    "ConfirmShipmentResult",
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
