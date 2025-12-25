# app/models/shipping_provider_zone_member.py
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ShippingProviderZoneMember(Base):
    __tablename__ = "shipping_provider_zone_members"
    __table_args__ = (
        UniqueConstraint("zone_id", "level", "value", name="uq_sp_zone_members_zone_level_value"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    zone_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("shipping_provider_zones.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # province/city/district/text
    level: Mapped[str] = mapped_column(String(16), nullable=False)
    value: Mapped[str] = mapped_column(String(64), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    zone = relationship("ShippingProviderZone", back_populates="members")

    def __repr__(self) -> str:
        return f"<ShippingProviderZoneMember id={self.id} zone_id={self.zone_id} {self.level}={self.value!r}>"
