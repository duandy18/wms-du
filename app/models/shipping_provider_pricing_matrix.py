# app/models/shipping_provider_pricing_matrix.py
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ShippingProviderPricingMatrix(Base):
    __tablename__ = "shipping_provider_pricing_matrix"
    __table_args__ = (
        CheckConstraint(
            "min_kg >= 0 AND (max_kg IS NULL OR max_kg > min_kg)",
            name="ck_sppm_range_valid",
        ),
        CheckConstraint(
            "pricing_mode in ('flat','linear_total','step_over','manual_quote')",
            name="ck_sppm_mode_valid",
        ),
        CheckConstraint(
            "pricing_mode <> 'flat' OR flat_amount IS NOT NULL",
            name="ck_sppm_flat_needs_flat_amount",
        ),
        CheckConstraint(
            "pricing_mode <> 'linear_total' OR rate_per_kg IS NOT NULL",
            name="ck_sppm_linear_needs_rate",
        ),
        CheckConstraint(
            """
            pricing_mode <> 'step_over'
            OR (
                base_kg IS NOT NULL
                AND base_amount IS NOT NULL
                AND rate_per_kg IS NOT NULL
            )
            """,
            name="ck_sppm_step_over_needs_fields",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    group_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("shipping_provider_destination_groups.id", ondelete="CASCADE"),
        nullable=False,
    )

    min_kg: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    max_kg: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 3), nullable=True)

    pricing_mode: Mapped[str] = mapped_column(String(32), nullable=False)

    flat_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    base_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    rate_per_kg: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4), nullable=True)
    base_kg: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 3), nullable=True)

    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

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

    group = relationship("ShippingProviderDestinationGroup", back_populates="matrix_rows")

    def __repr__(self) -> str:
        return (
            f"<ShippingProviderPricingMatrix id={self.id} group_id={self.group_id} "
            f"min={self.min_kg} max={self.max_kg} mode={self.pricing_mode}>"
        )
