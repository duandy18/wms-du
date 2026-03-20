# app/models/shipping_provider_pricing_template_module_range.py
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
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


class ShippingProviderPricingTemplateModuleRange(Base):
    __tablename__ = "shipping_provider_pricing_template_module_ranges"
    __table_args__ = (
        CheckConstraint(
            "min_kg >= 0 AND (max_kg IS NULL OR max_kg > min_kg)",
            name="ck_spptmr_range_valid",
        ),
        CheckConstraint(
            "default_pricing_mode in ('flat','linear_total','step_over','manual_quote')",
            name="ck_spptmr_default_mode_valid",
        ),
        UniqueConstraint("template_id", "sort_order", name="uq_spptmr_template_sort_order"),
        UniqueConstraint("template_id", "min_kg", "max_kg", name="uq_spptmr_template_range"),
        Index("ix_spptmr_template_id", "template_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    template_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("shipping_provider_pricing_templates.id", ondelete="CASCADE"),
        nullable=False,
    )

    min_kg: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    max_kg: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 3), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)

    default_pricing_mode: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="flat",
        server_default="flat",
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

    template = relationship(
        "ShippingProviderPricingTemplate",
        back_populates="ranges",
        lazy="selectin",
    )
    matrix_cells = relationship(
        "ShippingProviderPricingTemplateMatrix",
        back_populates="module_range",
        foreign_keys="ShippingProviderPricingTemplateMatrix.module_range_id",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"<ShippingProviderPricingTemplateModuleRange id={self.id} "
            f"template_id={self.template_id} min_kg={self.min_kg} max_kg={self.max_kg} "
            f"default_pricing_mode={self.default_pricing_mode!r}>"
        )
