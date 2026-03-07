# app/models/shipping_provider_surcharge.py
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ShippingProviderSurcharge(Base):
    __tablename__ = "shipping_provider_surcharges"
    __table_args__ = (
        UniqueConstraint("scheme_id", "name", name="uq_sp_surcharges_scheme_name"),
        CheckConstraint(
            "scope in ('province','city')",
            name="ck_sp_surcharges_scope_valid",
        ),
        CheckConstraint(
            """
            (
              (scope = 'province'
                AND (province_name IS NOT NULL OR province_code IS NOT NULL)
                AND city_name IS NULL
                AND city_code IS NULL
              )
              OR
              (scope = 'city'
                AND (province_name IS NOT NULL OR province_code IS NOT NULL)
                AND (city_name IS NOT NULL OR city_code IS NOT NULL)
              )
            )
            """,
            name="ck_sp_surcharges_scope_fields",
        ),
        CheckConstraint(
            "fixed_amount >= 0",
            name="ck_sp_surcharges_fixed_amount_required",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    scheme_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("shipping_provider_pricing_schemes.id", ondelete="RESTRICT"),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(String(128), nullable=False)

    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    scope: Mapped[str] = mapped_column(String(16), nullable=False)

    province_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    city_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    province_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    city_name: Mapped[str | None] = mapped_column(String(64), nullable=True)

    fixed_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    scheme = relationship("ShippingProviderPricingScheme", back_populates="surcharges")

    def __repr__(self) -> str:
        return (
            f"<ShippingProviderSurcharge id={self.id} scheme_id={self.scheme_id} "
            f"name={self.name!r} scope={self.scope!r}>"
        )
