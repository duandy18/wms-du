# app/models/lot.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Lot(Base):
    """
    Canonical Lot entity.

    结构关键点：
      - lot_id（Lot.id）是库存身份锚点，独立于 lot_code
      - lot_code == batch_code（展示/来源码），业务需防“输入漂移”
      - lots 冻结 item 侧关键主数据（policy），防主数据漂移污染历史解释链

    Phase M-5（结构治理：unit_governance 二阶段）：
      - 单位真相源 = item_uoms（结构层）
      - 冻结点 = PO/Receipt lines 的 *_ratio_to_base_snapshot + qty_base
      - lots 的单位快照列已物理移除（通过 Alembic migration）
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

    # 防批次漂移：lot_code 的归一化 key（至少 upper + trim）
    # DB migration: lot_code_key = upper(btrim(lot_code))
    lot_code_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

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
        # SUPPLIER lot：按归一化 key 唯一，防 lot_code 输入漂移（trim/upper）
        Index(
            "uq_lots_wh_item_lot_code_key",
            "warehouse_id",
            "item_id",
            "lot_code_key",
            unique=True,
            postgresql_where=text("lot_code IS NOT NULL"),
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
