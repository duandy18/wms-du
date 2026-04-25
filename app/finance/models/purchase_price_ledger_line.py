from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FinancePurchasePriceLedgerLine(Base):
    """
    财务侧 SKU / 商品采购价格核算明细表。

    定位：
    - 一行 = 一条 purchase_order_lines 采购发生；
    - 保留每次采购明细，不合并行；
    - 相同商品通过 item_id 分组汇集；
    - accounting_unit_price 不落库，由查询按当前筛选范围窗口聚合计算。
    """

    __tablename__ = "finance_purchase_price_ledger_lines"

    __table_args__ = (
        sa.UniqueConstraint(
            "po_line_id",
            name="uq_finance_purchase_price_ledger_lines_po_line_id",
        ),
        sa.Index("ix_fpp_ledger_item_id", "item_id"),
        sa.Index("ix_fpp_ledger_item_sku", "item_sku"),
        sa.Index("ix_fpp_ledger_supplier_id", "supplier_id"),
        sa.Index("ix_fpp_ledger_warehouse_id", "warehouse_id"),
        sa.Index("ix_fpp_ledger_purchase_date", "purchase_date"),
        sa.Index("ix_fpp_ledger_item_warehouse", "item_id", "warehouse_id"),
        sa.Index("ix_fpp_ledger_item_supplier", "item_id", "supplier_id"),
    )

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)

    po_line_id: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    po_id: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    po_no: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    line_no: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    item_id: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    item_sku: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    item_name: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    spec_text: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)

    supplier_id: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    supplier_name: Mapped[str] = mapped_column(sa.String(255), nullable=False)

    warehouse_id: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    warehouse_name: Mapped[str] = mapped_column(sa.String(100), nullable=False)

    purchase_time: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    purchase_date: Mapped[date] = mapped_column(sa.Date, nullable=False)

    qty_ordered_input: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    purchase_uom_name_snapshot: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    purchase_ratio_to_base_snapshot: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    qty_ordered_base: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    purchase_unit_price: Mapped[Decimal | None] = mapped_column(sa.Numeric(12, 2), nullable=True)
    planned_line_amount: Mapped[Decimal] = mapped_column(
        sa.Numeric(14, 2),
        nullable=False,
        server_default=sa.text("0"),
    )

    source_updated_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )
    calculated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )
