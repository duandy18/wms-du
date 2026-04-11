# app/models/lot.py
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Lot(Base):
    """
    Canonical Lot entity.

    结构关键点：
      - lot_id（Lot.id）是库存身份锚点，独立于 lot_code
      - lot_code 为展示/来源码，不再决定 lot 身份
      - lots 冻结 item 侧关键主数据（policy），防主数据漂移污染历史解释链

    Phase lot identity redesign：
      - REQUIRED 商品：lot 身份 = (warehouse_id, item_id, production_date)
      - NONE 商品：lot 身份 = INTERNAL singleton (warehouse_id, item_id)
      - lot_code 只保留为展示 / 输入 / 追溯属性
      - lots.production_date / lots.expiry_date 形成 canonical snapshot
      - stock_ledger.production_date / stock_ledger.expiry_date 继续保留为 RECEIPT event snapshot
    """

    __tablename__ = "lots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    warehouse_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False,
    )

    item_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("items.id", ondelete="RESTRICT"),
        nullable=False,
    )

    lot_code_source: Mapped[str] = mapped_column(String(16), nullable=False)

    # 展示/输入批次码（SUPPLIER lot 可填；INTERNAL lot 必须为 NULL）
    lot_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # REQUIRED 商品 lot 身份快照
    production_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # lot canonical 到期日期快照
    expiry_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    source_receipt_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("inbound_receipts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    source_line_no: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # ------------------------------------------------------------------
    # Item snapshots (frozen at lot creation time)
    # ------------------------------------------------------------------
    item_shelf_life_value_snapshot: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    item_shelf_life_unit_snapshot: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)

    item_lot_source_policy_snapshot: Mapped[str] = mapped_column(
        Enum("INTERNAL_ONLY", "SUPPLIER_ONLY", name="lot_source_policy"),
        nullable=False,
    )
    item_expiry_policy_snapshot: Mapped[str] = mapped_column(
        Enum("NONE", "REQUIRED", name="expiry_policy"),
        nullable=False,
    )
    item_derivation_allowed_snapshot: Mapped[bool] = mapped_column(Boolean, nullable=False)
    item_uom_governance_enabled_snapshot: Mapped[bool] = mapped_column(Boolean, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "lot_code_source IN ('SUPPLIER', 'INTERNAL')",
            name="ck_lots_lot_code_source",
        ),
        CheckConstraint(
            "("
            "item_shelf_life_unit_snapshot IS NULL OR "
            "(item_shelf_life_unit_snapshot IN ('DAY','WEEK','MONTH','YEAR'))"
            ")",
            name="ck_lots_item_shelf_life_unit_enum_snapshot",
        ),
        CheckConstraint(
            "((item_shelf_life_value_snapshot IS NULL) = (item_shelf_life_unit_snapshot IS NULL))",
            name="ck_lots_item_shelf_life_pair_snapshot",
        ),
        CheckConstraint(
            "("
            "item_expiry_policy_snapshot = 'REQUIRED' OR "
            "(item_shelf_life_value_snapshot IS NULL AND item_shelf_life_unit_snapshot IS NULL)"
            ")",
            name="ck_lots_sl_params_by_policy_snap",
        ),
        CheckConstraint(
            "("
            "(item_expiry_policy_snapshot = 'REQUIRED' AND production_date IS NOT NULL) OR "
            "(item_expiry_policy_snapshot <> 'REQUIRED' AND production_date IS NULL)"
            ")",
            name="ck_lots_production_date_by_expiry_policy",
        ),
        CheckConstraint(
            "("
            "production_date IS NULL OR "
            "expiry_date IS NULL OR "
            "production_date <= expiry_date"
            ")",
            name="ck_lots_production_le_expiry",
        ),
        CheckConstraint(
            "("
            "item_expiry_policy_snapshot <> 'REQUIRED' OR "
            "lot_code_source <> 'SUPPLIER' OR "
            "expiry_date IS NOT NULL"
            ")",
            name="ck_lots_required_supplier_expiry_not_null",
        ),
        CheckConstraint(
            "("
            "item_expiry_policy_snapshot <> 'REQUIRED' OR "
            "lot_code_source = 'SUPPLIER'"
            ")",
            name="ck_lots_required_supplier_source",
        ),
        # REQUIRED lot：按 (warehouse_id,item_id,production_date) 唯一
        Index(
            "uq_lots_required_single_wh_item_prod",
            "warehouse_id",
            "item_id",
            "production_date",
            unique=True,
            postgresql_where=text(
                "lot_code_source = 'SUPPLIER' "
                "AND item_expiry_policy_snapshot = 'REQUIRED' "
                "AND production_date IS NOT NULL"
            ),
        ),
        # INTERNAL lot：每 (warehouse,item) 单例（lot_code 必须为 NULL）
        Index(
            "uq_lots_internal_single_wh_item",
            "warehouse_id",
            "item_id",
            unique=True,
            postgresql_where=text("lot_code_source = 'INTERNAL' AND lot_code IS NULL"),
        ),
    )
