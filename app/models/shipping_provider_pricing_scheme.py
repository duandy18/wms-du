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

# ✅ 新增：模板模型（路线 1）
from app.models.shipping_provider_pricing_scheme_segment_template import (  # noqa: F401
    ShippingProviderPricingSchemeSegmentTemplate,
)
from app.models.shipping_provider_pricing_scheme_segment_template_item import (  # noqa: F401
    ShippingProviderPricingSchemeSegmentTemplateItem,
)

# ✅ Phase 3：起运适用仓库（origin binding）关系表模型加载
from app.models.shipping_provider_pricing_scheme_warehouse import (  # noqa: F401
    ShippingProviderPricingSchemeWarehouse,
)


class ShippingProviderPricingScheme(Base):
    __tablename__ = "shipping_provider_pricing_schemes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

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

    # ✅ 方案默认口径（方案级：一套表一个口径）
    default_pricing_mode: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="linear_total",
        server_default="linear_total",
    )

    billable_weight_rule: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # ✅ Phase 4.3：列结构（重量分段模板）方案级真相（后端落库）
    # ⚠️ 继续保留该字段用于兼容/镜像（由“启用模板”同步写回）
    segments_json: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    segments_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # ✅ Phase 6：刚性关系（用于 SchemeOut.shipping_provider_name）
    # - 不改 DB schema，只补 ORM relationship
    # - lazy=selectin 与本模块其余关系一致（避免 N+1，且不靠隐式 lazy）
    shipping_provider = relationship("ShippingProvider", lazy="selectin")

    zones = relationship("ShippingProviderZone", back_populates="scheme", lazy="selectin")
    surcharges = relationship("ShippingProviderSurcharge", back_populates="scheme", lazy="selectin")

    # ✅ Phase 3：显式关系（方案适用哪些仓作为起运地）
    scheme_warehouses: Mapped[list["ShippingProviderPricingSchemeWarehouse"]] = relationship(
        "ShippingProviderPricingSchemeWarehouse",
        back_populates="scheme",
        lazy="selectin",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # ✅ 现有：段表 relationship（前端当前仍在使用）
    segments = relationship(
        "ShippingProviderPricingSchemeSegment",
        back_populates="scheme",
        lazy="selectin",
        order_by="ShippingProviderPricingSchemeSegment.ord.asc()",
        cascade="all, delete-orphan",
    )

    # ✅ 新增：模板列表（路线 1 的真相）
    segment_templates = relationship(
        "ShippingProviderPricingSchemeSegmentTemplate",
        back_populates="scheme",
        lazy="selectin",
        order_by="ShippingProviderPricingSchemeSegmentTemplate.id.asc()",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<ShippingProviderPricingScheme id={self.id} provider_id={self.shipping_provider_id} name={self.name!r}>"
