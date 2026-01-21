# app/models/shipping_provider_pricing_scheme_warehouse.py
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ShippingProviderPricingSchemeWarehouse(Base):
    """
    Phase 3：起运适用仓库（origin binding）事实表

    语义：
    - 这套运价方案（scheme）适用于该仓库作为起运地
    - 这是事实边界，不是策略
    """

    __tablename__ = "shipping_provider_pricing_scheme_warehouses"
    __table_args__ = (UniqueConstraint("scheme_id", "warehouse_id", name="uq_sp_scheme_wh_scheme_warehouse"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    scheme_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("shipping_provider_pricing_schemes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    warehouse_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true", index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # ✅ 方案端显式 relationship
    scheme = relationship(
        "ShippingProviderPricingScheme",
        back_populates="scheme_warehouses",
        lazy="selectin",
    )

    # ✅ 仓库端显式 relationship
    warehouse = relationship(
        "Warehouse",
        back_populates="pricing_scheme_warehouses",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"<ShippingProviderPricingSchemeWarehouse id={self.id} "
            f"scheme_id={self.scheme_id} warehouse_id={self.warehouse_id} active={self.active}>"
        )
