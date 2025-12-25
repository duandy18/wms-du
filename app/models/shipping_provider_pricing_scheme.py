# app/models/shipping_provider_pricing_scheme.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ShippingProviderPricingScheme(Base):
    __tablename__ = "shipping_provider_pricing_schemes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    shipping_provider_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("shipping_providers.id", ondelete="RESTRICT"),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(String(128), nullable=False)

    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    priority: Mapped[int] = mapped_column(
        Integer, nullable=False, default=100, server_default="100"
    )

    currency: Mapped[str] = mapped_column(
        String(8), nullable=False, default="CNY", server_default="CNY"
    )

    effective_from: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    effective_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # ✅ 方案默认口径（方案级：一套表一个口径）
    # - 允许值由 DB CHECK 约束控制（见 Alembic）
    # - API 侧额外约束：不允许 manual_quote 作为默认口径
    default_pricing_mode: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="linear_total",
        server_default="linear_total",
    )

    # 计费重量规则：{"divisor_cm":8000,"rounding":{"mode":"ceil","step_kg":1.0},...}
    billable_weight_rule: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # ✅ Phase 4.3：列结构（重量分段模板）方案级真相（后端落库）
    # 形状示例：[{ "min":"0", "max":"1" }, { "min":"1", "max":"2" }, { "min":"2", "max":"" }]
    segments_json: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    # ✅ Phase 4.3：列结构更新时间（用于复现/对账/提示）
    segments_updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # relationships
    zones = relationship("ShippingProviderZone", back_populates="scheme", lazy="selectin")
    surcharges = relationship("ShippingProviderSurcharge", back_populates="scheme", lazy="selectin")

    def __repr__(self) -> str:
        return f"<ShippingProviderPricingScheme id={self.id} provider_id={self.shipping_provider_id} name={self.name!r}>"
