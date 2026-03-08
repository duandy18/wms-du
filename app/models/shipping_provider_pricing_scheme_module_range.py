# app/models/shipping_provider_pricing_scheme_module_range.py
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Numeric, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ShippingProviderPricingSchemeModuleRange(Base):
    __tablename__ = "shipping_provider_pricing_scheme_module_ranges"
    __table_args__ = (
        CheckConstraint(
            "min_kg >= 0 AND (max_kg IS NULL OR max_kg > min_kg)",
            name="ck_sppsmr_range_valid",
        ),
        UniqueConstraint("module_id", "sort_order", name="uq_sppsmr_module_sort_order"),
        UniqueConstraint("module_id", "min_kg", "max_kg", name="uq_sppsmr_module_range"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    module_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("shipping_provider_pricing_scheme_modules.id", ondelete="CASCADE"),
        nullable=False,
    )

    min_kg: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    max_kg: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 3), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    module = relationship("ShippingProviderPricingSchemeModule", back_populates="ranges")
    matrix_cells = relationship(
        "ShippingProviderPricingMatrix",
        back_populates="module_range",
        foreign_keys="ShippingProviderPricingMatrix.module_range_id",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"<ShippingProviderPricingSchemeModuleRange id={self.id} "
            f"module_id={self.module_id} min_kg={self.min_kg} max_kg={self.max_kg}>"
        )
