# app/models/shipping_provider_surcharge_config.py
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


class ShippingProviderSurchargeConfig(Base):
    __tablename__ = "shipping_provider_surcharge_configs"
    __table_args__ = (
        UniqueConstraint(
            "scheme_id",
            "province_code",
            name="uq_sp_surcharge_configs_scheme_province",
        ),
        CheckConstraint(
            "province_mode in ('province','cities')",
            name="ck_sp_surcharge_configs_province_mode",
        ),
        CheckConstraint(
            "fixed_amount >= 0",
            name="ck_sp_surcharge_configs_fixed_amount",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    scheme_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("shipping_provider_pricing_schemes.id", ondelete="CASCADE"),
        nullable=False,
    )

    province_code: Mapped[str] = mapped_column(String(32), nullable=False)
    province_name: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # province = 全省收费
    # cities   = 仅指定城市收费，省内其他城市不收费
    province_mode: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="province",
        server_default="province",
    )

    # 仅 province_mode=province 时使用
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

    scheme = relationship(
        "ShippingProviderPricingScheme",
        back_populates="surcharge_configs",
    )

    cities = relationship(
        "ShippingProviderSurchargeConfigCity",
        back_populates="config",
        lazy="selectin",
        cascade="all, delete-orphan",
        order_by="ShippingProviderSurchargeConfigCity.id.asc()",
    )

    def __repr__(self) -> str:
        return (
            f"<ShippingProviderSurchargeConfig id={self.id} "
            f"scheme_id={self.scheme_id} province_code={self.province_code!r} "
            f"province_mode={self.province_mode!r}>"
        )
