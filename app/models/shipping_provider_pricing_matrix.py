from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ShippingProviderPricingMatrix(Base):
    __tablename__ = "shipping_provider_pricing_matrix"
    __table_args__ = (
        UniqueConstraint(
            "group_id",
            "module_range_id",
            name="uq_sppm_group_module_range",
        ),
        CheckConstraint(
            "pricing_mode in ('flat','linear_total','step_over','manual_quote')",
            name="ck_sppm_mode_valid",
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
            name="ck_sppm_flat_shape",
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
            name="ck_sppm_linear_total_shape",
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
            name="ck_sppm_step_over_shape",
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
            name="ck_sppm_manual_quote_shape",
        ),
        ForeignKeyConstraint(
            ["group_id", "range_module_id"],
            ["shipping_provider_destination_groups.id", "shipping_provider_destination_groups.module_id"],
            ondelete="CASCADE",
            name="fk_sppm_group_same_module",
        ),
        ForeignKeyConstraint(
            ["module_range_id", "range_module_id"],
            [
                "shipping_provider_pricing_scheme_module_ranges.id",
                "shipping_provider_pricing_scheme_module_ranges.module_id",
            ],
            ondelete="CASCADE",
            name="fk_sppm_range_same_module",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    group_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("shipping_provider_destination_groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    pricing_mode: Mapped[str] = mapped_column(String(32), nullable=False)

    flat_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    base_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    rate_per_kg: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4), nullable=True)
    base_kg: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 3), nullable=True)

    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    module_range_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("shipping_provider_pricing_scheme_module_ranges.id", ondelete="CASCADE"),
        nullable=False,
    )

    range_module_id: Mapped[int] = mapped_column(
        Integer,
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
        "ShippingProviderDestinationGroup",
        back_populates="matrix_rows",
        foreign_keys=[group_id],
    )
    module_range = relationship(
        "ShippingProviderPricingSchemeModuleRange",
        foreign_keys=[module_range_id],
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"<ShippingProviderPricingMatrix id={self.id} "
            f"group_id={self.group_id} "
            f"module_range_id={self.module_range_id} "
            f"mode={self.pricing_mode}>"
        )
