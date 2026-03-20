# app/models/shipping_provider_pricing_template_surcharge_config_city.py
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


class ShippingProviderPricingTemplateSurchargeConfigCity(Base):
    __tablename__ = "shipping_provider_pricing_template_surcharge_config_cities"
    __table_args__ = (
        UniqueConstraint(
            "config_id",
            "city_code",
            name="uq_spptscc_city",
        ),
        CheckConstraint(
            "fixed_amount >= 0",
            name="ck_spptscc_fixed_amount",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    config_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("shipping_provider_pricing_template_surcharge_configs.id", ondelete="CASCADE"),
        nullable=False,
    )

    city_code: Mapped[str] = mapped_column(String(32), nullable=False)
    city_name: Mapped[str | None] = mapped_column(String(64), nullable=True)

    fixed_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=0,
        server_default="0",
    )

    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
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

    config = relationship(
        "ShippingProviderPricingTemplateSurchargeConfig",
        back_populates="cities",
    )

    def __repr__(self) -> str:
        return (
            f"<ShippingProviderPricingTemplateSurchargeConfigCity id={self.id} "
            f"config_id={self.config_id} city_code={self.city_code!r}>"
        )
