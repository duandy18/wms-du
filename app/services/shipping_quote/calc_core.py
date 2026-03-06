# app/services/shipping_quote/calc_core.py
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.shipping_provider_pricing_scheme import ShippingProviderPricingScheme


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
    Route A 合同（硬仓库边界）：
    - scheme 的作用域 = warehouse × provider（shipping_provider_pricing_schemes.warehouse_id）
    - 因此不再存在 scheme_warehouses 绑定表，也不允许通过“绑定行 active”做第二套开关。

    允许条件（严格）：
    - scheme.id == scheme_id
    - scheme.warehouse_id == warehouse_id
    - scheme.active == true
    - scheme.archived_at IS NULL（已归档不应参与算价）
    """
    sch = (
        db.query(ShippingProviderPricingScheme)
        .filter(ShippingProviderPricingScheme.id == int(scheme_id))
        .first()
    )
    if not sch:
        raise ValueError("scheme not found")

    if int(getattr(sch, "warehouse_id")) != int(warehouse_id):
        raise ValueError("scheme not allowed for warehouse (warehouse mismatch)")

    if not bool(sch.active):
        raise ValueError("scheme inactive")

    if getattr(sch, "archived_at", None) is not None:
        raise ValueError("scheme archived")
