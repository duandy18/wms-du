# app/shipping_assist/providers/models/shipping_provider.py
# Domain move: shipping provider ORM belongs to TMS providers.
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.db.base import Base


class ShippingProvider(Base):
    """
    运输网点实体（保留表名 shipping_providers）

    语义说明：
    - 本表一行 = 实际合作的运输网点（非快递公司总部）
    - 与仓库为 M:N 关系，通过 warehouse_shipping_providers 表表达
    - code 为内部业务键（可修改，但仍需规范化且全局唯一）
    - company_code / resource_code 为电子面单固定接入参数，不承载店铺维度配置
    """

    __tablename__ = "shipping_providers"
    __table_args__ = (
        UniqueConstraint("name", name="uq_shipping_providers_name"),
        UniqueConstraint("code", name="uq_shipping_providers_code"),
        {"info": {"skip_autogen": True}},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # 内部业务键（DB 侧仍保持：NOT NULL + UNIQUE + upper/trim）
    code: Mapped[str] = mapped_column(String(64), nullable=False)

    # 电子面单固定接入参数（非店铺维度）
    company_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resource_code: Mapped[str | None] = mapped_column(String(64), nullable=True)

    address: Mapped[str | None] = mapped_column(String(255), nullable=True)

    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )

    priority: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=100,
        server_default="100",
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

    contacts = relationship(
        "ShippingProviderContact",
        back_populates="shipping_provider",
        lazy="selectin",
        order_by="(desc(ShippingProviderContact.is_primary), ShippingProviderContact.id)",
    )

    warehouse_shipping_providers = relationship(
        "WarehouseShippingProvider",
        back_populates="shipping_provider",
        lazy="selectin",
        passive_deletes=True,
    )

    @validates("code")
    def _validate_code(self, _key: str, value: str) -> str:
        if value is None:
            raise ValueError("shipping_provider.code 不能为空")
        v = value.strip().upper()
        if v == "":
            raise ValueError("shipping_provider.code 不能为空白")
        return v

    @validates("name")
    def _validate_name(self, _key: str, value: str) -> str:
        if value is None:
            raise ValueError("shipping_provider.name 不能为空")
        v = value.strip()
        if v == "":
            raise ValueError("shipping_provider.name 不能为空白")
        return v

    def __repr__(self) -> str:
        return f"<ShippingProvider id={self.id} name={self.name!r} active={self.active}>"
