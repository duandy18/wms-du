# app/services/shipping_quote/calc_core.py
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.shipping_provider_pricing_scheme import ShippingProviderPricingScheme
from app.models.shipping_provider_pricing_scheme_warehouse import ShippingProviderPricingSchemeWarehouse


def scheme_is_effective(sch: ShippingProviderPricingScheme, now: datetime) -> bool:
    if not bool(sch.active):
        return False
    if sch.effective_from is not None and sch.effective_from > now:
        return False
    if sch.effective_to is not None and sch.effective_to < now:
        return False
    return True


def check_scheme_warehouse_allowed(db: Session, scheme_id: int, warehouse_id: int) -> None:
    """
    Phase 4.x 合同：scheme 必须显式绑定起运仓，且绑定 active=true 才允许算价。
    """
    row = (
        db.query(ShippingProviderPricingSchemeWarehouse)
        .filter(
            ShippingProviderPricingSchemeWarehouse.scheme_id == int(scheme_id),
            ShippingProviderPricingSchemeWarehouse.warehouse_id == int(warehouse_id),
        )
        .first()
    )
    if not row:
        raise ValueError("scheme not allowed for warehouse (missing scheme-warehouse binding)")
    if not bool(row.active):
        raise ValueError("scheme warehouse binding inactive")
