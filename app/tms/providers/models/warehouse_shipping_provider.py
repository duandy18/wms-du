# app/tms/providers/models/warehouse_shipping_provider.py
# Domain move: warehouse shipping provider binding ORM belongs to TMS providers.
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
from app.tms.pricing.templates.models.shipping_provider_pricing_template import ShippingProviderPricingTemplate  # noqa: F401


class WarehouseShippingProvider(Base):
    """
    仓库 × 快递公司（ShippingProvider）运行态绑定

    语义：
    - 一行表示：某仓库当前配置了一家快递公司
    - active 是运行开关（启用 / 停用）
    - active_template_id 是运行态单锚点：当前挂载的运价模板
    - effective_from 是启用生效时间：
      1) NULL 表示立即生效 / 历史已生效数据
      2) > now 表示待生效
      3) <= now 表示已生效
    - disabled_at 记录最近一次停用时间（仅用于运行展示 / 审计，不参与算价）
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

    active_template_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("shipping_provider_pricing_templates.id", ondelete="SET NULL"),
        nullable=True,
    )

    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )

    effective_from: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    disabled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
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
    active_template = relationship(
        "ShippingProviderPricingTemplate",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"<WarehouseShippingProvider id={self.id} "
            f"warehouse_id={self.warehouse_id} provider_id={self.shipping_provider_id} "
            f"active_template_id={self.active_template_id} "
            f"active={self.active} effective_from={self.effective_from!r}>"
        )
