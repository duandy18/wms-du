# app/models/warehouse_shipping_provider.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class WarehouseShippingProvider(Base):
    """
    仓库 × 快递公司（ShippingProvider）能力集合：事实绑定（Phase 1）

    语义：
    - 一行表示：某仓库「事实层面可用」某快递公司
    - active 是事实开关（可用/禁用）
    - priority 仅用于仓库侧展示排序（不是推荐/算价策略）
    - pickup_cutoff_time / remark 为可选运维字段（不进入算价）
    """

    __tablename__ = "warehouse_shipping_providers"
    __table_args__ = (
        UniqueConstraint(
            "warehouse_id",
            "shipping_provider_id",
            name="uq_wh_shipping_providers_wh_provider",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    warehouse_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("warehouses.id", ondelete="CASCADE"),
        nullable=False,
    )

    shipping_provider_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("shipping_providers.id", ondelete="RESTRICT"),
        nullable=False,
    )

    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )

    # 仅用于仓库侧展示排序（不用于 quote/ranking）
    priority: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    # 简化：用 "HH:MM" 字符串，避免引入时区/日期语义
    pickup_cutoff_time: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)

    remark: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

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

    warehouse = relationship(
        "Warehouse",
        back_populates="warehouse_shipping_providers",
        lazy="selectin",
    )
    shipping_provider = relationship(
        "ShippingProvider",
        back_populates="warehouse_shipping_providers",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"<WarehouseShippingProvider id={self.id} "
            f"warehouse_id={self.warehouse_id} provider_id={self.shipping_provider_id} "
            f"active={self.active}>"
        )
