# app/models/shipping_provider_zone_bracket.py
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ShippingProviderZoneBracket(Base):
    __tablename__ = "shipping_provider_zone_brackets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    zone_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("shipping_provider_zones.id", ondelete="RESTRICT"),
        nullable=False,
    )

    min_kg: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    max_kg: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 3), nullable=True
    )  # null = infinity

    # =========================================================
    # 查表模型（唯一主路径，不考虑兼容）
    #
    # pricing_mode:
    #   - flat         : 整段定价（元/票），使用 flat_amount
    #   - linear_total : 面单费/基础费（base_amount, 元/票） + 总计费重×单价（rate_per_kg, 元/kg）
    #                   amount = base_amount + rate_per_kg * billable_weight_kg
    #   - step_over    : 首重/续重（base_kg/base_amount/rate_per_kg）
    #   - manual_quote : 人工报价（不自动算）
    # =========================================================
    pricing_mode: Mapped[str] = mapped_column(String(32), nullable=False, server_default="flat")

    flat_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)

    # linear_total / step_over：base_amount / rate_per_kg
    base_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    rate_per_kg: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4), nullable=True)

    # step_over：首重（kg）
    base_kg: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 3), nullable=True)

    # Mirror field (DB enforced): jsonb NOT NULL
    # - maintained by trigger: trg_spzb_sync_price_json / spzb_sync_price_json()
    price_json: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)

    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    zone = relationship("ShippingProviderZone", back_populates="brackets")

    def __repr__(self) -> str:
        return (
            f"<ShippingProviderZoneBracket id={self.id} zone_id={self.zone_id} "
            f"{self.min_kg}-{self.max_kg} mode={self.pricing_mode}>"
        )
