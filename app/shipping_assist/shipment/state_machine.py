# app/shipping_assist/shipment/state_machine.py
# 分拆说明：
# - 本文件新增 Shipment 状态机规则层；
# - 目标是统一 Shipment 合法状态集合与状态转移约束；
# - 当前阶段只收口第一版最小状态集合，不承载持久化/审计/事务。
from __future__ import annotations

from .contracts import ShipmentApplicationError

SHIPMENT_STATUSES = {
    "IN_TRANSIT",
    "DELIVERED",
    "LOST",
    "RETURNED",
}

FINAL_SHIPMENT_STATUSES = {
    "DELIVERED",
    "LOST",
    "RETURNED",
}

ALLOWED_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "IN_TRANSIT": {"DELIVERED", "LOST", "RETURNED"},
    "DELIVERED": set(),
    "LOST": set(),
    "RETURNED": set(),
}


def _raise(*, status_code: int, code: str, message: str) -> None:
    raise ShipmentApplicationError(
        status_code=status_code,
        code=code,
        message=message,
    )


def ensure_shipment_status_value(status: str) -> str:
    normalized = status.strip().upper()
    if normalized not in SHIPMENT_STATUSES:
        _raise(
            status_code=422,
            code="SHIPMENT_STATUS_INVALID",
            message=f"invalid shipment status: {status}",
        )
    return normalized


def ensure_shipment_status_transition(
    *,
    old_status: str | None,
    new_status: str,
) -> None:
    normalized_new = ensure_shipment_status_value(new_status)

    if old_status is None:
        return

    normalized_old = ensure_shipment_status_value(old_status)
    if normalized_old == normalized_new:
        return

    allowed_next = ALLOWED_STATUS_TRANSITIONS.get(normalized_old, set())
    if normalized_new not in allowed_next:
        _raise(
            status_code=409,
            code="SHIPMENT_STATUS_TRANSITION_INVALID",
            message=f"invalid shipment status transition: {normalized_old} -> {normalized_new}",
        )
