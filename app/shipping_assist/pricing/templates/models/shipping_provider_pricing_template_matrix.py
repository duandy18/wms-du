# app/shipping_assist/pricing/templates/models/shipping_provider_pricing_template_matrix.py
# Domain move: pricing template matrix ORM belongs to TMS pricing templates.
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ShippingProviderPricingTemplateMatrix(Base):
    __tablename__ = "shipping_provider_pricing_template_matrix"
    __table_args__ = (
        UniqueConstraint(
            "group_id",
            "module_range_id",
            name="uq_spptm_group_module_range",
        ),
        Index("ix_spptm_group_id", "group_id"),
        CheckConstraint(
            "pricing_mode in ('flat','linear_total','step_over','manual_quote')",
            name="ck_spptm_mode_valid",
        ),
        CheckConstraint(
            """
            pricing_mode <> 'flat'
            OR (
                flat_amount IS NOT NULL
                AND base_amount IS NULL
                AND rate_per_kg IS NULL
                AND base_kg IS NULL
            )
            """,
            name="ck_spptm_flat_shape",
        ),
        CheckConstraint(
            """
            pricing_mode <> 'linear_total'
            OR (
                flat_amount IS NULL
                AND base_amount IS NOT NULL
                AND rate_per_kg IS NOT NULL
                AND base_kg IS NULL
            )
            """,
            name="ck_spptm_linear_total_shape",
        ),
        CheckConstraint(
            """
            pricing_mode <> 'step_over'
            OR (
                flat_amount IS NULL
                AND base_kg IS NOT NULL
                AND base_amount IS NOT NULL
                AND rate_per_kg IS NOT NULL
            )
            """,
            name="ck_spptm_step_over_shape",
        ),
        CheckConstraint(
            """
            pricing_mode <> 'manual_quote'
            OR (
                flat_amount IS NULL
                AND base_amount IS NULL
                AND rate_per_kg IS NULL
                AND base_kg IS NULL
            )
            """,
            name="ck_spptm_manual_quote_shape",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    group_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("shipping_provider_pricing_template_destination_groups.id", ondelete="CASCADE"),
        nullable=False,
    )

    pricing_mode: Mapped[str] = mapped_column(String(32), nullable=False)

    flat_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    base_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    rate_per_kg: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4), nullable=True)
    base_kg: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 3), nullable=True)

    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    module_range_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("shipping_provider_pricing_template_module_ranges.id", ondelete="CASCADE"),
        nullable=False,
    )

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

    group = relationship(
        "ShippingProviderPricingTemplateDestinationGroup",
        back_populates="matrix_rows",
        foreign_keys=[group_id],
    )
    module_range = relationship(
        "ShippingProviderPricingTemplateModuleRange",
        back_populates="matrix_cells",
        foreign_keys=[module_range_id],
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"<ShippingProviderPricingTemplateMatrix id={self.id} "
            f"group_id={self.group_id} "
            f"module_range_id={self.module_range_id} "
            f"mode={self.pricing_mode}>"
        )
