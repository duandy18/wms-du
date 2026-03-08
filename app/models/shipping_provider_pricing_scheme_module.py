# app/models/shipping_provider_pricing_scheme_module.py
from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ShippingProviderPricingSchemeModule(Base):
    __tablename__ = "shipping_provider_pricing_scheme_modules"
    __table_args__ = (
        CheckConstraint(
            "module_code in ('standard','other')",
            name="ck_sppsm_module_code_valid",
        ),
        UniqueConstraint("scheme_id", "module_code", name="uq_sppsm_scheme_module_code"),
        UniqueConstraint("scheme_id", "sort_order", name="uq_sppsm_scheme_sort_order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    scheme_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("shipping_provider_pricing_schemes.id", ondelete="CASCADE"),
        nullable=False,
    )

    module_code: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
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

    scheme = relationship("ShippingProviderPricingScheme", back_populates="modules")
    ranges = relationship(
        "ShippingProviderPricingSchemeModuleRange",
        back_populates="module",
        lazy="selectin",
        cascade="all, delete-orphan",
    )
    destination_groups = relationship(
        "ShippingProviderDestinationGroup",
        back_populates="module",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<ShippingProviderPricingSchemeModule id={self.id} "
            f"scheme_id={self.scheme_id} module_code={self.module_code!r}>"
        )
