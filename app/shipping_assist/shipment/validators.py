# app/shipping_assist/shipment/validators.py
# 分拆说明：
# - 本文件从 service.py 中拆出 Shipment 前置校验与执行前一致性校验；
# - 目标是让 service.py 只保留应用编排，不再混杂 SQL 校验细节。
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .contracts import ShipmentApplicationError


def _raise(*, status_code: int, code: str, message: str) -> None:
    raise ShipmentApplicationError(
        status_code=status_code,
        code=code,
        message=message,
    )


async def load_active_provider(session: AsyncSession, shipping_provider_id: int) -> dict[str, object]:
    row = (
        await session.execute(
            text(
                """
                SELECT
                  id,
                  code,
                  name,
                  company_code,
                  resource_code,
                  active
                FROM shipping_providers
                WHERE id = :pid
                LIMIT 1
                """
            ),
            {"pid": shipping_provider_id},
        )
    ).mappings().first()

    if not row or not bool(row.get("active", True)):
        _raise(
            status_code=409,
            code="SHIP_WITH_WAYBILL_CARRIER_NOT_AVAILABLE",
            message="carrier not available",
        )

    return dict(row)


async def ensure_warehouse_binding(
    session: AsyncSession,
    *,
    warehouse_id: int,
    shipping_provider_id: int,
) -> None:
    row = (
        await session.execute(
            text(
                """
                SELECT 1
                FROM warehouse_shipping_providers
                WHERE warehouse_id = :wid
                  AND shipping_provider_id = :pid
                  AND active = true
                LIMIT 1
                """
            ),
            {"wid": warehouse_id, "pid": shipping_provider_id},
        )
    ).first()

    if row is None:
        _raise(
            status_code=409,
            code="SHIP_WITH_WAYBILL_CARRIER_NOT_ENABLED_FOR_WAREHOUSE",
            message="carrier not enabled for this warehouse",
        )


def ensure_quote_snapshot_provider_matches(
    quote_snapshot: dict[str, object],
    *,
    shipping_provider_id: int,
) -> None:
    selected_quote = quote_snapshot.get("selected_quote")
    if not isinstance(selected_quote, dict):
        _raise(
            status_code=422,
            code="SHIP_WITH_WAYBILL_SELECTED_QUOTE_REQUIRED",
            message="meta.quote_snapshot.selected_quote is required",
        )

    provider_id = selected_quote.get("provider_id")
    if not isinstance(provider_id, int):
        _raise(
            status_code=422,
            code="SHIP_WITH_WAYBILL_QUOTE_PROVIDER_REQUIRED",
            message="meta.quote_snapshot.selected_quote.provider_id is required",
        )

    if provider_id != int(shipping_provider_id):
        _raise(
            status_code=422,
            code="SHIP_WITH_WAYBILL_QUOTE_PROVIDER_MISMATCH",
            message="quote_snapshot provider_id does not match shipping_provider_id",
        )
