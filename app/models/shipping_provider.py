# app/models/shipping_provider.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates
from sqlalchemy import inspect as sa_inspect

from app.db.base import Base


class ShippingProvider(Base):
    """
    运输网点实体（保留表名 shipping_providers）

    语义说明：
    - 本表一行 = 实际合作的运输网点（非快递公司总部）
    - 与仓库为 M:N 关系，通过 warehouse_shipping_providers 表表达
    - code 为内部业务键（不可变、规范化）
    - external_outlet_code 为外部网点号（展示/对接用，可空、可改）
    """

    __tablename__ = "shipping_providers"
    __table_args__ = (
        UniqueConstraint("name", name="uq_shipping_providers_name"),
        UniqueConstraint("code", name="uq_shipping_providers_code"),
        {"info": {"skip_autogen": True}},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # 内部业务键（已在 DB 侧强约束：NOT NULL + UNIQUE + upper/trim + 不可变 trigger）
    code: Mapped[str] = mapped_column(String(64), nullable=False)

    # 外部网点号：展示/对接用（可空、可改）
    external_outlet_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    address: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

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

        state = sa_inspect(self)
        if state.persistent:
            old = getattr(self, "code", None)
            if old is not None and v != old:
                raise ValueError("shipping_provider.code 不允许修改（创建后不可变）")
        return v

    @validates("external_outlet_code")
    def _validate_external_outlet_code(self, _key: str, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        v = value.strip()
        return v if v != "" else None

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
