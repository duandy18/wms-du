# app/models/shipping_provider_pricing_scheme.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ShippingProviderPricingScheme(Base):
    __tablename__ = "shipping_provider_pricing_schemes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Route A：硬仓库边界（scheme 作用域 = warehouse × provider）
    warehouse_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False,
    )

    shipping_provider_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("shipping_providers.id", ondelete="RESTRICT"),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(String(128), nullable=False)

    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    # 归档：archived_at != null => 已归档（不删除，保留历史解释器）
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="CNY", server_default="CNY")

    effective_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # 方案默认口径
    default_pricing_mode: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="linear_total",
        server_default="linear_total",
    )

    billable_weight_rule: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # =========================
    # relationships
    # =========================

    shipping_provider = relationship("ShippingProvider", lazy="selectin")
    warehouse = relationship("Warehouse", lazy="selectin")

    # surcharge-only（含目的地附加费）
    surcharges = relationship("ShippingProviderSurcharge", back_populates="scheme", lazy="selectin")

    def __repr__(self) -> str:
        return (
            f"<ShippingProviderPricingScheme id={self.id} "
            f"warehouse_id={self.warehouse_id} provider_id={self.shipping_provider_id} name={self.name!r}>"
        )
