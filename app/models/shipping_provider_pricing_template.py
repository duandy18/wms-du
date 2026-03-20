# app/models/shipping_provider_pricing_template.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ShippingProviderPricingTemplate(Base):
    __tablename__ = "shipping_provider_pricing_templates"
    __table_args__ = (
        CheckConstraint(
            "status in ('draft','active','archived')",
            name="ck_sppt_status_valid",
        ),
        CheckConstraint(
            "billable_weight_strategy in ('actual_only','max_actual_volume')",
            name="ck_sppt_billable_strategy",
        ),
        CheckConstraint(
            "rounding_mode in ('none','ceil')",
            name="ck_sppt_rounding_mode",
        ),
        CheckConstraint(
            "default_pricing_mode in ('flat','linear_total','step_over','manual_quote')",
            name="ck_sppt_default_pricing_mode",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    shipping_provider_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("shipping_providers.id", ondelete="RESTRICT"),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(String(128), nullable=False)

    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="draft",
        server_default="draft",
    )

    archived_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    currency: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
        default="CNY",
        server_default="CNY",
    )

    effective_from: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    effective_to: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    default_pricing_mode: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="linear_total",
        server_default="linear_total",
    )

    billable_weight_strategy: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="actual_only",
        server_default="actual_only",
    )
    volume_divisor: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rounding_mode: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="none",
        server_default="none",
    )
    rounding_step_kg: Mapped[Optional[float]] = mapped_column(Numeric(10, 3), nullable=True)
    min_billable_weight_kg: Mapped[Optional[float]] = mapped_column(Numeric(10, 3), nullable=True)

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

    shipping_provider = relationship("ShippingProvider", lazy="selectin")

    ranges = relationship(
        "ShippingProviderPricingTemplateModuleRange",
        back_populates="template",
        lazy="selectin",
        cascade="all, delete-orphan",
    )
    destination_groups = relationship(
        "ShippingProviderPricingTemplateDestinationGroup",
        back_populates="template",
        lazy="selectin",
        cascade="all, delete-orphan",
    )
    surcharge_configs = relationship(
        "ShippingProviderPricingTemplateSurchargeConfig",
        back_populates="template",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<ShippingProviderPricingTemplate id={self.id} "
            f"provider_id={self.shipping_provider_id} "
            f"status={self.status} "
            f"name={self.name!r}>"
        )
