# app/services/shipping_quote/calc_core.py
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.shipping_provider_pricing_scheme import ShippingProviderPricingScheme


def scheme_is_effective(sch: ShippingProviderPricingScheme, now: datetime) -> bool:
    if str(getattr(sch, "status", "")).strip().lower() != "active":
        return False
    if getattr(sch, "archived_at", None) is not None:
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
    - 不再存在 scheme_warehouses 绑定表
    - 允许参与算价的 scheme 必须满足：
      1) warehouse_id 匹配
      2) status = active
      3) archived_at IS NULL
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

    if str(getattr(sch, "status", "")).strip().lower() != "active":
        raise ValueError("scheme not active")

    if getattr(sch, "archived_at", None) is not None:
        raise ValueError("scheme archived")
