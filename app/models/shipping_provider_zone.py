# app/models/shipping_provider_zone.py
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ShippingProviderZone(Base):
    __tablename__ = "shipping_provider_zones"
    __table_args__ = (UniqueConstraint("scheme_id", "name", name="uq_sp_zones_scheme_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    scheme_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("shipping_provider_pricing_schemes.id", ondelete="RESTRICT"),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(String(128), nullable=False)

    priority: Mapped[int] = mapped_column(
        Integer, nullable=False, default=100, server_default="100"
    )
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    scheme = relationship("ShippingProviderPricingScheme", back_populates="zones")

    members = relationship("ShippingProviderZoneMember", back_populates="zone", lazy="selectin")
    brackets = relationship("ShippingProviderZoneBracket", back_populates="zone", lazy="selectin")

    def __repr__(self) -> str:
        return f"<ShippingProviderZone id={self.id} scheme_id={self.scheme_id} name={self.name!r}>"
