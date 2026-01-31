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

    ✅ Phase: code 化（最终口径）
    - scope: 'province' | 'city'
    - 幂等 key（事实主键口径）：(scheme_id, scope, province_code, city_code)
      - scope=province 时 city_code 必须为 NULL
    - 互斥规则（省 vs 市）仍由 service 层硬约束保证

    ✅ 兼容期：
    - legacy 字段 province/city 暂留（历史数据 / 旧入口兜底）
    - 新写入优先使用 province_code/city_code
    """

    __tablename__ = "pricing_scheme_dest_adjustments"
    __table_args__ = (
        UniqueConstraint(
            "scheme_id",
            "scope",
            "province_code",
            "city_code",
            name="uq_scheme_dest_adj_scope_provcode_citycode",
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

    # ✅ 新：事实 key（稳定口径）
    province_code: Mapped[str] = mapped_column(String(32), nullable=False)
    city_code: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # ✅ 新：展示冗余（便于 explain/UI；也方便未来对齐 code->name）
    province_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    city_name: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # ✅ 兼容旧字段：历史入口（字符串世界）
    province: Mapped[str] = mapped_column(String(64), nullable=False)
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
            f"scope={self.scope} "
            f"province_code={self.province_code!r} city_code={self.city_code!r} "
            f"province_name={self.province_name!r} city_name={self.city_name!r}>"
        )
