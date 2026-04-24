# app/tms/pricing/templates/models/shipping_provider_pricing_template_destination_group.py
# Domain move: pricing template destination group ORM belongs to TMS pricing templates.
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ShippingProviderPricingTemplateDestinationGroup(Base):
    __tablename__ = "shipping_provider_pricing_template_destination_groups"
    __table_args__ = (
        UniqueConstraint("template_id", "sort_order", name="uq_spptdg_template_sort_order"),
        Index("ix_spptdg_template_id", "template_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    template_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("shipping_provider_pricing_templates.id", ondelete="CASCADE"),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
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

    template = relationship(
        "ShippingProviderPricingTemplate",
        back_populates="destination_groups",
        lazy="selectin",
    )
    members = relationship(
        "ShippingProviderPricingTemplateDestinationGroupMember",
        back_populates="group",
        lazy="selectin",
        cascade="all, delete-orphan",
    )
    matrix_rows = relationship(
        "ShippingProviderPricingTemplateMatrix",
        back_populates="group",
        foreign_keys="ShippingProviderPricingTemplateMatrix.group_id",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<ShippingProviderPricingTemplateDestinationGroup id={self.id} "
            f"template_id={self.template_id} name={self.name!r}>"
        )
