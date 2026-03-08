from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ShippingProviderDestinationGroup(Base):
    __tablename__ = "shipping_provider_destination_groups"
    __table_args__ = (
        UniqueConstraint("module_id", "name", name="uq_sp_dest_groups_module_name"),
        UniqueConstraint("module_id", "sort_order", name="uq_sp_dest_groups_module_sort_order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    scheme_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("shipping_provider_pricing_schemes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    module_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("shipping_provider_pricing_scheme_modules.id", ondelete="CASCADE"),
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

    scheme = relationship("ShippingProviderPricingScheme", lazy="selectin")
    module = relationship("ShippingProviderPricingSchemeModule", lazy="selectin")
    members = relationship(
        "ShippingProviderDestinationGroupMember",
        back_populates="group",
        lazy="selectin",
        cascade="all, delete-orphan",
    )
    matrix_rows = relationship(
        "ShippingProviderPricingMatrix",
        back_populates="group",
        foreign_keys="ShippingProviderPricingMatrix.group_id",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<ShippingProviderDestinationGroup id={self.id} "
            f"scheme_id={self.scheme_id} module_id={self.module_id} name={self.name!r}>"
        )
