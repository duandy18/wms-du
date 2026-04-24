# app/tms/pricing/templates/models/shipping_provider_pricing_template.py
# Domain move: pricing template ORM belongs to TMS pricing templates.
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ShippingProviderPricingTemplate(Base):
    __tablename__ = "shipping_provider_pricing_templates"
    __table_args__ = (
        CheckConstraint(
            "status in ('draft','archived')",
            name="ck_sppt_status_valid",
        ),
        CheckConstraint(
            "validation_status in ('not_validated','passed','failed')",
            name="ck_sppt_validation_status",
        ),
        CheckConstraint(
            """
            (status = 'draft' AND archived_at IS NULL)
            OR
            (status = 'archived' AND archived_at IS NOT NULL)
            """,
            name="ck_sppt_archived_state_consistent",
        ),
        CheckConstraint(
            "expected_ranges_count > 0",
            name="ck_sppt_expected_ranges_count_positive",
        ),
        CheckConstraint(
            "expected_groups_count > 0",
            name="ck_sppt_expected_groups_count_positive",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    shipping_provider_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("shipping_providers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    source_template_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("shipping_provider_pricing_templates.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(128), nullable=False)

    expected_ranges_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    expected_groups_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="draft",
        server_default="draft",
        index=True,
    )

    archived_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    validation_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="not_validated",
        server_default="not_validated",
        index=True,
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

    shipping_provider = relationship("ShippingProvider", lazy="selectin")

    source_template = relationship(
        "ShippingProviderPricingTemplate",
        remote_side="ShippingProviderPricingTemplate.id",
        lazy="selectin",
    )

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
            f"source_template_id={self.source_template_id} "
            f"status={self.status} "
            f"validation_status={self.validation_status} "
            f"expected_ranges_count={self.expected_ranges_count} "
            f"expected_groups_count={self.expected_groups_count} "
            f"name={self.name!r}>"
        )
