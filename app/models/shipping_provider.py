# app/models/shipping_provider.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ShippingProvider(Base):
    """
    物流 / 快递公司主数据（Phase 3 定型）

    裁决：
    - 主表只承载主体事实（name/code/active/priority/pricing_model/region_rules）
    - 联系人事实在 shipping_provider_contacts 子表
    - ORM 必须保留 contacts relationship（供读聚合 & 其他模块引用）
    """

    __tablename__ = "shipping_providers"
    __table_args__ = (
        UniqueConstraint("name", name="uq_shipping_providers_name"),
        UniqueConstraint("code", name="uq_shipping_providers_code"),
        {"info": {"skip_autogen": True}},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )

    # 运价 / 发货相关
    priority: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=100,
        server_default="100",
    )
    pricing_model: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    region_rules: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

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

    # ✅ 必须存在：与 ShippingProviderContact.back_populates="shipping_provider" 对应
    contacts = relationship(
        "ShippingProviderContact",
        back_populates="shipping_provider",
        lazy="selectin",
        order_by="(desc(ShippingProviderContact.is_primary), ShippingProviderContact.id)",
    )

    def __repr__(self) -> str:
        return f"<ShippingProvider id={self.id} name={self.name!r} active={self.active}>"
