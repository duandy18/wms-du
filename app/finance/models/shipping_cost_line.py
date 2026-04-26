from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FinanceShippingCostLine(Base):
    """
    财务侧物流成本核算明细表。

    定位：
    - 一行 = 一条 shipping_records 发货包裹事实；
    - 第一阶段只承载预计物流成本；
    - 实际账单 / 对账 / 利润分析后置，不混入本表第一版主合同。
    """

    __tablename__ = "finance_shipping_cost_lines"

    __table_args__ = (
        sa.UniqueConstraint(
            "shipping_record_id",
            name="uq_finance_shipping_cost_lines_shipping_record_id",
        ),
        sa.Index("ix_fsc_lines_platform_shop", "platform", "shop_id"),
        sa.Index("ix_fsc_lines_shop_id", "shop_id"),
        sa.Index("ix_fsc_lines_warehouse_id", "warehouse_id"),
        sa.Index("ix_fsc_lines_provider_id", "shipping_provider_id"),
        sa.Index("ix_fsc_lines_provider_code", "shipping_provider_code"),
        sa.Index("ix_fsc_lines_tracking_no", "tracking_no"),
        sa.Index("ix_fsc_lines_order_ref", "order_ref"),
        sa.Index("ix_fsc_lines_shipped_date", "shipped_date"),
    )

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)

    shipping_record_id: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)

    platform: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    shop_id: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    shop_name: Mapped[str | None] = mapped_column(sa.String(256), nullable=True)

    order_ref: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    package_no: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    tracking_no: Mapped[str | None] = mapped_column(sa.String(128), nullable=True)

    warehouse_id: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    warehouse_name: Mapped[str] = mapped_column(sa.String(100), nullable=False)

    shipping_provider_id: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    shipping_provider_code: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    shipping_provider_name: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)

    shipped_time: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    shipped_date: Mapped[date] = mapped_column(sa.Date, nullable=False)

    dest_province: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    dest_city: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)

    gross_weight_kg: Mapped[Decimal | None] = mapped_column(sa.Numeric(10, 3), nullable=True)
    cost_estimated: Mapped[Decimal | None] = mapped_column(sa.Numeric(12, 2), nullable=True)

    source_updated_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )
    calculated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )
