# app/models/shipping_provider_pricing_scheme.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# ✅ 确保 Segment 模型被加载到 ORM registry
from app.models.shipping_provider_pricing_scheme_segment import (  # noqa: F401
    ShippingProviderPricingSchemeSegment,
)

# ✅ 模板模型
from app.models.shipping_provider_pricing_scheme_segment_template import (  # noqa: F401
    ShippingProviderPricingSchemeSegmentTemplate,
)
from app.models.shipping_provider_pricing_scheme_segment_template_item import (  # noqa: F401
    ShippingProviderPricingSchemeSegmentTemplateItem,
)


class ShippingProviderPricingScheme(Base):
    __tablename__ = "shipping_provider_pricing_schemes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # ✅ Route A：硬仓库边界（scheme 作用域 = warehouse × provider）
    warehouse_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False,
    )

    shipping_provider_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("shipping_providers.id", ondelete="RESTRICT"),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(String(128), nullable=False)

    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    # ✅ 归档：archived_at != null => 已归档（不删除，保留历史解释器）
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="CNY", server_default="CNY")

    effective_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # ✅ 方案默认口径
    default_pricing_mode: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="linear_total",
        server_default="linear_total",
    )

    billable_weight_rule: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # ✅ 兼容字段：scheme 级 segments_json
    segments_json: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    segments_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # ✅ 显式默认回退模板
    default_segment_template_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("shipping_provider_pricing_scheme_segment_templates.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # =========================
    # relationships
    # =========================

    shipping_provider = relationship("ShippingProvider", lazy="selectin")
    warehouse = relationship("Warehouse", lazy="selectin")

    zones = relationship("ShippingProviderZone", back_populates="scheme", lazy="selectin")

    # surcharge-only（含目的地附加费）
    surcharges = relationship("ShippingProviderSurcharge", back_populates="scheme", lazy="selectin")

    # 现有：段表
    segments = relationship(
        "ShippingProviderPricingSchemeSegment",
        back_populates="scheme",
        lazy="selectin",
        order_by="ShippingProviderPricingSchemeSegment.ord.asc()",
        cascade="all, delete-orphan",
    )

    # 模板列表
    segment_templates = relationship(
        "ShippingProviderPricingSchemeSegmentTemplate",
        back_populates="scheme",
        lazy="selectin",
        order_by="ShippingProviderPricingSchemeSegmentTemplate.id.asc()",
        cascade="all, delete-orphan",
        foreign_keys="ShippingProviderPricingSchemeSegmentTemplate.scheme_id",
    )

    default_segment_template = relationship(
        "ShippingProviderPricingSchemeSegmentTemplate",
        lazy="selectin",
        foreign_keys=[default_segment_template_id],
        post_update=True,
    )

    def __repr__(self) -> str:
        return (
            f"<ShippingProviderPricingScheme id={self.id} "
            f"warehouse_id={self.warehouse_id} provider_id={self.shipping_provider_id} name={self.name!r}>"
        )
