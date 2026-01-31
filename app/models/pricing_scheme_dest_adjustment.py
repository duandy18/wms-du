# app/models/pricing_scheme_dest_adjustment.py
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class PricingSchemeDestAdjustment(Base):
    """
    目的地附加费（结构化定价事实）

    裁决：
    - scope: 'province' | 'city'
    - 同一 scheme + scope + province + city 唯一
    - 互斥规则（省 vs 市）在 service 层保证
    """

    __tablename__ = "pricing_scheme_dest_adjustments"
    __table_args__ = (
        UniqueConstraint(
            "scheme_id",
            "scope",
            "province",
            "city",
            name="uq_scheme_dest_adj_scope_province_city",
        ),
        CheckConstraint(
            "scope in ('province','city')",
            name="ck_scheme_dest_adj_scope",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    scheme_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("shipping_provider_pricing_schemes.id", ondelete="CASCADE"),
        nullable=False,
    )

    # 'province' | 'city'
    scope: Mapped[str] = mapped_column(String(16), nullable=False)

    province: Mapped[str] = mapped_column(String(64), nullable=False)

    # city 仅在 scope='city' 时允许非空
    city: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # 第一阶段只支持 flat
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)

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

    scheme = relationship(
        "ShippingProviderPricingScheme",
        back_populates="dest_adjustments",
    )

    def __repr__(self) -> str:
        return (
            f"<PricingSchemeDestAdjustment "
            f"id={self.id} scheme_id={self.scheme_id} "
            f"scope={self.scope} province={self.province!r} city={self.city!r}>"
        )
