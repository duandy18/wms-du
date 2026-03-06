# app/models/shipping_provider_destination_group_member.py
from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ShippingProviderDestinationGroupMember(Base):
    __tablename__ = "shipping_provider_destination_group_members"
    __table_args__ = (
        CheckConstraint(
            "scope in ('province','city')",
            name="ck_sp_dest_group_members_scope_valid",
        ),
        CheckConstraint(
            """
            (
              scope = 'province'
              AND (province_name IS NOT NULL OR province_code IS NOT NULL)
              AND city_name IS NULL
              AND city_code IS NULL
            )
            OR
            (
              scope = 'city'
              AND (province_name IS NOT NULL OR province_code IS NOT NULL)
              AND (city_name IS NOT NULL OR city_code IS NOT NULL)
            )
            """,
            name="ck_sp_dest_group_members_scope_fields",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    group_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("shipping_provider_destination_groups.id", ondelete="CASCADE"),
        nullable=False,
    )

    scope: Mapped[str] = mapped_column(String(16), nullable=False)

    province_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    city_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    province_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    city_name: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    group = relationship("ShippingProviderDestinationGroup", back_populates="members")

    def __repr__(self) -> str:
        return (
            f"<ShippingProviderDestinationGroupMember id={self.id} group_id={self.group_id} "
            f"scope={self.scope!r} province={self.province_name or self.province_code!r} "
            f"city={self.city_name or self.city_code!r}>"
        )
