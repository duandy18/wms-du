# app/tms/quote_snapshot/validator.py
from __future__ import annotations

from .contracts import QUOTE_SNAPSHOT_VERSION
from app.tms.shipment.contracts import ShipmentApplicationError


def extract_quote_snapshot(meta: dict[str, object] | None) -> dict[str, object]:
    if meta is None:
        return {}
    raw = meta.get("quote_snapshot")
    if isinstance(raw, dict):
        return dict(raw)
    return {}


def validate_quote_snapshot(quote_snapshot: dict[str, object]) -> None:
    version = quote_snapshot.get("version")
    if version is not None and str(version) != QUOTE_SNAPSHOT_VERSION:
        raise ShipmentApplicationError(
            status_code=422,
            code="SHIP_WITH_WAYBILL_QUOTE_SNAPSHOT_VERSION_INVALID",
            message=f"meta.quote_snapshot.version must be {QUOTE_SNAPSHOT_VERSION}",
        )

    selected_quote_raw = quote_snapshot.get("selected_quote")
    if not isinstance(selected_quote_raw, dict):
        raise ShipmentApplicationError(
            status_code=422,
            code="SHIP_WITH_WAYBILL_SELECTED_QUOTE_REQUIRED",
            message="meta.quote_snapshot.selected_quote is required",
        )

    total_amount = selected_quote_raw.get("total_amount")
    if not isinstance(total_amount, (int, float)):
        raise ShipmentApplicationError(
            status_code=422,
            code="SHIP_WITH_WAYBILL_TOTAL_AMOUNT_INVALID",
            message="meta.quote_snapshot.selected_quote.total_amount must be number",
        )

    reasons = selected_quote_raw.get("reasons")
    if not isinstance(reasons, list) or len(reasons) == 0:
        raise ShipmentApplicationError(
            status_code=422,
            code="SHIP_WITH_WAYBILL_REASONS_REQUIRED",
            message="meta.quote_snapshot.selected_quote.reasons must be non-empty list",
        )


def extract_cost_estimated(quote_snapshot: dict[str, object]) -> float:
    selected_quote = quote_snapshot.get("selected_quote")
    if not isinstance(selected_quote, dict):
        raise ShipmentApplicationError(
            status_code=422,
            code="SHIP_WITH_WAYBILL_SELECTED_QUOTE_REQUIRED",
            message="meta.quote_snapshot.selected_quote is required",
        )

    total_amount = selected_quote.get("total_amount")
    if not isinstance(total_amount, (int, float)):
        raise ShipmentApplicationError(
            status_code=422,
            code="SHIP_WITH_WAYBILL_TOTAL_AMOUNT_INVALID",
            message="meta.quote_snapshot.selected_quote.total_amount must be number",
        )

    return float(total_amount)
