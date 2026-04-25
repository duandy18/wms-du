# app/shipping_assist/pricing/templates/models/shipping_provider_pricing_template_destination_group_member.py
# Domain move: pricing template destination group member ORM belongs to TMS pricing templates.
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ShippingProviderPricingTemplateDestinationGroupMember(Base):
    __tablename__ = "shipping_provider_pricing_template_destination_group_members"
    __table_args__ = (
        CheckConstraint(
            "(province_name IS NOT NULL OR province_code IS NOT NULL)",
            name="ck_spptdgm_province_required",
        ),
        Index(
            "uq_spptdgm_group_province_key",
            "group_id",
            text("COALESCE(province_code, '')"),
            text("COALESCE(province_name, '')"),
            unique=True,
        ),
        Index(
            "ix_spptdgm_group_province",
            "group_id",
            "province_code",
            "province_name",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    group_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("shipping_provider_pricing_template_destination_groups.id", ondelete="CASCADE"),
        nullable=False,
    )

    province_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    province_name: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    group = relationship(
        "ShippingProviderPricingTemplateDestinationGroup",
        back_populates="members",
    )

    def __repr__(self) -> str:
        return (
            f"<ShippingProviderPricingTemplateDestinationGroupMember id={self.id} "
            f"group_id={self.group_id} province={self.province_name or self.province_code!r}>"
        )
