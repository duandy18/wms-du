# app/shipping_assist/providers/models/electronic_waybill_config.py
# Domain move: electronic waybill config ORM belongs to TMS providers.
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.db.base import Base


class ElectronicWaybillConfig(Base):
    """
    店铺维度电子面单配置

    语义说明：
    - 一行 = 某平台某店铺在某快递网点下的一套电子面单配置
    - shipping_provider_id 指向运输网点主档（固定接入参数在 shipping_providers）
    - customer_code / sender_* 属于店铺维度配置真相
    """

    __tablename__ = "electronic_waybill_configs"
    __table_args__ = (
        UniqueConstraint(
            "platform",
            "store_code",
            "shipping_provider_id",
            name="uq_electronic_waybill_configs_platform_store_provider",
        ),
        Index("ix_electronic_waybill_configs_shipping_provider_id", "shipping_provider_id"),
        Index("ix_electronic_waybill_configs_platform_store", "platform", "store_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    store_code: Mapped[str] = mapped_column(String(64), nullable=False)

    shipping_provider_id: Mapped[int] = mapped_column(
        ForeignKey("shipping_providers.id", ondelete="RESTRICT"),
        nullable=False,
    )

    customer_code: Mapped[str] = mapped_column(String(64), nullable=False)

    sender_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sender_mobile: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sender_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sender_province: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sender_city: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sender_district: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sender_address: Mapped[str | None] = mapped_column(String(255), nullable=True)

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

    shipping_provider = relationship(
        "ShippingProvider",
        lazy="selectin",
    )

    @validates("platform")
    def _validate_platform(self, _key: str, value: str) -> str:
        if value is None:
            raise ValueError("electronic_waybill_configs.platform 不能为空")
        v = value.strip().upper()
        if v == "":
            raise ValueError("electronic_waybill_configs.platform 不能为空白")
        return v

    @validates("store_code")
    def _validate_store_code(self, _key: str, value: str) -> str:
        if value is None:
            raise ValueError("electronic_waybill_configs.store_code 不能为空")
        v = value.strip()
        if v == "":
            raise ValueError("electronic_waybill_configs.store_code 不能为空白")
        return v

    @validates("customer_code")
    def _validate_customer_code(self, _key: str, value: str) -> str:
        if value is None:
            raise ValueError("electronic_waybill_configs.customer_code 不能为空")
        v = value.strip()
        if v == "":
            raise ValueError("electronic_waybill_configs.customer_code 不能为空白")
        return v

    def __repr__(self) -> str:
        return (
            f"<ElectronicWaybillConfig id={self.id} "
            f"platform={self.platform!r} store_code={self.store_code!r} "
            f"shipping_provider_id={self.shipping_provider_id} active={self.active}>"
        )
