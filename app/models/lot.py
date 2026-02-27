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
    Phase 2: Canonical Lot entity.

    SUPPLIER:
      - lot_code 必填
      - source_receipt_id/source_line_no 必须为 NULL

    INTERNAL:
      - source_receipt_id/source_line_no 必填（绑定来源 receipt_id + line_no）
      - lot_code 允许 NULL

    Snapshot 规则：
      - lot 是库存维度事实锚点，必须冻结 item 侧关键主数据，避免主数据漂移污染历史解释链。
      - 本模型不使用 mapped_column(index=True) 生成隐式索引，索引以 migration 为准。

    Phase M：
      - 冻结 items.policy 到 lots（防漂移封板）
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

    # 'SUPPLIER' | 'INTERNAL'
    lot_code_source: Mapped[str] = mapped_column(String(16), nullable=False)

    lot_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    source_receipt_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("inbound_receipts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    source_line_no: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    production_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # 'EXPLICIT' | 'DERIVED' | NULL
    expiry_source: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)

    shelf_life_days_applied: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # ------------------------------------------------------------------
    # Item snapshots (frozen at lot creation time)
    # ------------------------------------------------------------------

    # 旧字段（已被 Phase M 迁移锁死为 expiry_policy 的镜像字段）
    item_has_shelf_life_snapshot: Mapped[Optional[bool]] = mapped_column(nullable=True)

    item_shelf_life_value_snapshot: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    item_shelf_life_unit_snapshot: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)

    item_uom_snapshot: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    item_case_ratio_snapshot: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    item_case_uom_snapshot: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)

    # Phase M：规则层 snapshot（DB 已 NOT NULL）
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
        # ---------------------------
        # Core checks (Phase 2)
        # ---------------------------
        CheckConstraint(
            "lot_code_source IN ('SUPPLIER', 'INTERNAL')",
            name="ck_lots_lot_code_source",
        ),
        CheckConstraint(
            "("
            "lot_code_source <> 'SUPPLIER' OR "
            "(lot_code IS NOT NULL AND source_receipt_id IS NULL AND source_line_no IS NULL)"
            ")",
            name="ck_lots_supplier_requires_lot_code_and_no_source",
        ),
        CheckConstraint(
            "("
            "lot_code_source <> 'INTERNAL' OR "
            "(source_receipt_id IS NOT NULL AND source_line_no IS NOT NULL)"
            ")",
            name="ck_lots_internal_requires_source",
        ),
        CheckConstraint(
            "(" "expiry_source IS NULL OR expiry_source IN ('EXPLICIT', 'DERIVED')" ")",
            name="ck_lots_expiry_source_enum",
        ),
        # ---------------------------
        # Snapshot checks (align with items constraints)
        # ---------------------------
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
            "item_has_shelf_life_snapshot IS NULL OR "
            "item_has_shelf_life_snapshot = true OR "
            "(item_shelf_life_value_snapshot IS NULL AND item_shelf_life_unit_snapshot IS NULL)"
            ")",
            name="ck_lots_item_shelf_life_params_only_when_enabled_snapshot",
        ),
        CheckConstraint(
            "(item_case_ratio_snapshot IS NULL OR item_case_ratio_snapshot >= 1)",
            name="ck_lots_item_case_ratio_ge_1_snapshot",
        ),
        # ---------------------------
        # Partial unique indexes (canonical identity)
        # ---------------------------
        Index(
            "uq_lots_supplier_wh_item_lot_code",
            "warehouse_id",
            "item_id",
            "lot_code_source",
            "lot_code",
            unique=True,
            postgresql_where=text("lot_code_source = 'SUPPLIER'"),
        ),
        Index(
            "uq_lots_internal_wh_item_source",
            "warehouse_id",
            "item_id",
            "lot_code_source",
            "source_receipt_id",
            "source_line_no",
            unique=True,
            postgresql_where=text("lot_code_source = 'INTERNAL'"),
        ),
    )
