from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FinanceOrderSalesLine(Base):
    """
    财务侧订单销售核算明细表。

    定位：
    - 一行 = 一个 order_items.id 销售订单行；
    - 主源来自 orders + order_items + stores + order_address；
    - 不读取 order_lines 作为销售金额主源；
    - 不读取 platform_order_lines 作为财务金额主源；
    - order_ref 用于后续与物流成本事实表按订单维度闭环。
    """

    __tablename__ = "finance_order_sales_lines"

    __table_args__ = (
        sa.UniqueConstraint(
            "order_item_id",
            name="uq_finance_order_sales_lines_order_item_id",
        ),
        sa.Index("ix_fosl_order_id", "order_id"),
        sa.Index("ix_fosl_order_item_id", "order_item_id"),
        sa.Index("ix_fosl_platform_store", "platform", "store_code"),
        sa.Index("ix_fosl_store_id", "store_id"),
        sa.Index("ix_fosl_store_code", "store_code"),
        sa.Index("ix_fosl_order_ref", "order_ref"),
        sa.Index("ix_fosl_ext_order_no", "ext_order_no"),
        sa.Index("ix_fosl_order_date", "order_date"),
        sa.Index("ix_fosl_item_id", "item_id"),
        sa.Index("ix_fosl_sku_id", "sku_id"),
    )

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)

    order_id: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    order_item_id: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)

    platform: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    store_id: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    store_code: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    store_name: Mapped[str | None] = mapped_column(sa.String(256), nullable=True)

    ext_order_no: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    order_ref: Mapped[str] = mapped_column(sa.String(256), nullable=False)
    order_status: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)

    order_created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    order_date: Mapped[date] = mapped_column(sa.Date, nullable=False)

    receiver_province: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    receiver_city: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    receiver_district: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)

    item_id: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    sku_id: Mapped[str | None] = mapped_column(sa.String(128), nullable=True)
    title: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)

    qty_sold: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        server_default=sa.text("0"),
    )
    unit_price: Mapped[Decimal | None] = mapped_column(sa.Numeric(12, 2), nullable=True)
    discount_amount: Mapped[Decimal | None] = mapped_column(sa.Numeric(12, 2), nullable=True)
    line_amount: Mapped[Decimal] = mapped_column(
        sa.Numeric(14, 2),
        nullable=False,
        server_default=sa.text("0"),
    )

    order_amount: Mapped[Decimal | None] = mapped_column(sa.Numeric(14, 2), nullable=True)
    pay_amount: Mapped[Decimal | None] = mapped_column(sa.Numeric(14, 2), nullable=True)

    source_updated_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )
    calculated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )
