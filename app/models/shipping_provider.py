# app/models/shipping_provider.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ShippingProvider(Base):
    """
    仓库可用快递网点（Phase 6 语义升级）

    裁决：
    - 本表一行 = 服务某仓库区域、参与运费比价的最小单元（快递网点）
    - 必须绑定 warehouse_id（单仓归属）
    - 联系人事实在 shipping_provider_contacts 子表
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

    # ✅ 网点地址（可选）：用于揽收/交接/诊断
    address: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )

    # ✅ 单仓归属（刚性）
    warehouse_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False,
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

    # 可选：便于读/诊断（不影响 API）
    warehouse = relationship("Warehouse", lazy="selectin")

    def __repr__(self) -> str:
        return f"<ShippingProvider id={self.id} name={self.name!r} active={self.active} warehouse_id={self.warehouse_id}>"
