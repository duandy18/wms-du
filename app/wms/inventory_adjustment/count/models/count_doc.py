# app/wms/inventory_adjustment/count/models/count_doc.py
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class CountDoc(Base):
    """
    盘点单头（inventory_adjustment.count 主线）

    设计原则：
    - 盘点单头锚定 warehouse_id + snapshot_at
    - snapshot_at 是盘点时点唯一真相源
    - posted_event_id 是后续正式 COUNT 事件的桥接锚点
    """

    __tablename__ = "count_docs"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)

    count_no: Mapped[str] = mapped_column(sa.String(64), nullable=False)

    warehouse_id: Mapped[int] = mapped_column(
        sa.Integer,
        sa.ForeignKey("warehouses.id", name="fk_count_docs_warehouse", ondelete="RESTRICT"),
        nullable=False,
    )

    snapshot_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        sa.String(16),
        nullable=False,
        default="DRAFT",
        server_default="DRAFT",
        index=True,
    )

    posted_event_id: Mapped[Optional[int]] = mapped_column(
        sa.Integer,
        sa.ForeignKey("wms_events.id", name="fk_count_docs_posted_event", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    created_by: Mapped[Optional[int]] = mapped_column(
        sa.Integer,
        sa.ForeignKey("users.id", name="fk_count_docs_created_by", ondelete="SET NULL"),
        nullable=True,
    )

    remark: Mapped[Optional[str]] = mapped_column(sa.String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )

    counted_at: Mapped[Optional[datetime]] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )

    posted_at: Mapped[Optional[datetime]] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )

    lines: Mapped[List["CountDocLine"]] = relationship(
        "CountDocLine",
        back_populates="doc",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        sa.UniqueConstraint("count_no", name="uq_count_docs_count_no"),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'FROZEN', 'COUNTED', 'POSTED', 'VOIDED')",
            name="ck_count_docs_status",
        ),
        sa.Index("ix_count_docs_warehouse_snapshot_at", "warehouse_id", "snapshot_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<CountDoc id={self.id} count_no={self.count_no} "
            f"warehouse_id={self.warehouse_id} status={self.status} "
            f"snapshot_at={self.snapshot_at} posted_event_id={self.posted_event_id}>"
        )


class CountDocLine(Base):
    """
    盘点单明细（商品级）

    设计原则：
    - 主锚点是 item_id，不再以 lot_id 作为盘点主行业务锚点
    - 这是一张“商品级即时库存快照 + 实盘录入 + 差异处理”的单据行
    - lot 分布下沉到 CountDocLineLotSnapshot
    """

    __tablename__ = "count_doc_lines"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)

    doc_id: Mapped[int] = mapped_column(
        sa.Integer,
        sa.ForeignKey("count_docs.id", name="fk_count_doc_lines_doc", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    line_no: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    item_id: Mapped[int] = mapped_column(
        sa.Integer,
        sa.ForeignKey("items.id", name="fk_count_doc_lines_item", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    item_name_snapshot: Mapped[Optional[str]] = mapped_column(sa.String(255), nullable=True)
    item_spec_snapshot: Mapped[Optional[str]] = mapped_column(sa.String(255), nullable=True)

    snapshot_qty_base: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    counted_item_uom_id: Mapped[Optional[int]] = mapped_column(
        sa.Integer,
        nullable=True,
        index=True,
    )
    counted_uom_name_snapshot: Mapped[Optional[str]] = mapped_column(sa.String(64), nullable=True)
    counted_ratio_to_base_snapshot: Mapped[Optional[int]] = mapped_column(sa.Integer, nullable=True)
    counted_qty_input: Mapped[Optional[int]] = mapped_column(sa.Integer, nullable=True)

    counted_qty_base: Mapped[Optional[int]] = mapped_column(sa.Integer, nullable=True)
    diff_qty_base: Mapped[Optional[int]] = mapped_column(sa.Integer, nullable=True)

    reason_code: Mapped[Optional[str]] = mapped_column(
        sa.String(32),
        nullable=True,
        index=True,
    )

    disposition: Mapped[Optional[str]] = mapped_column(
        sa.String(32),
        nullable=True,
        index=True,
    )

    remark: Mapped[Optional[str]] = mapped_column(sa.String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )

    doc: Mapped["CountDoc"] = relationship(
        "CountDoc",
        back_populates="lines",
        lazy="selectin",
    )

    lot_snapshots: Mapped[List["CountDocLineLotSnapshot"]] = relationship(
        "CountDocLineLotSnapshot",
        back_populates="line",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["counted_item_uom_id", "item_id"],
            ["item_uoms.id", "item_uoms.item_id"],
            name="fk_count_doc_lines_counted_item_uom_pair",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("doc_id", "line_no", name="uq_count_doc_lines_doc_line"),
        sa.UniqueConstraint("doc_id", "item_id", name="uq_count_doc_lines_doc_item"),
        sa.CheckConstraint(
            "line_no >= 1",
            name="ck_count_doc_lines_line_no_positive",
        ),
        sa.CheckConstraint(
            "snapshot_qty_base >= 0",
            name="ck_count_doc_lines_snapshot_qty_base_nonneg",
        ),
        sa.CheckConstraint(
            "counted_qty_input IS NULL OR counted_qty_input >= 0",
            name="ck_count_doc_lines_counted_qty_input_nonneg",
        ),
        sa.CheckConstraint(
            "counted_qty_base IS NULL OR counted_qty_base >= 0",
            name="ck_count_doc_lines_counted_qty_base_nonneg",
        ),
        sa.CheckConstraint(
            "counted_ratio_to_base_snapshot IS NULL OR counted_ratio_to_base_snapshot >= 1",
            name="ck_count_doc_lines_counted_ratio_positive",
        ),
        sa.CheckConstraint(
            """
            (
              counted_item_uom_id IS NULL
              AND counted_uom_name_snapshot IS NULL
              AND counted_ratio_to_base_snapshot IS NULL
              AND counted_qty_input IS NULL
              AND counted_qty_base IS NULL
              AND diff_qty_base IS NULL
            )
            OR
            (
              counted_item_uom_id IS NOT NULL
              AND counted_uom_name_snapshot IS NOT NULL
              AND counted_ratio_to_base_snapshot IS NOT NULL
              AND counted_qty_input IS NOT NULL
              AND counted_qty_base IS NOT NULL
              AND diff_qty_base IS NOT NULL
              AND counted_qty_base = (counted_qty_input * counted_ratio_to_base_snapshot)
              AND diff_qty_base = (counted_qty_base - snapshot_qty_base)
            )
            """,
            name="ck_count_doc_lines_count_payload_consistent",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<CountDocLine id={self.id} doc_id={self.doc_id} line_no={self.line_no} "
            f"item_id={self.item_id} snapshot_qty_base={self.snapshot_qty_base} "
            f"counted_item_uom_id={self.counted_item_uom_id} "
            f"counted_qty_input={self.counted_qty_input} "
            f"counted_qty_base={self.counted_qty_base} "
            f"diff_qty_base={self.diff_qty_base}>"
        )


class CountDocLineLotSnapshot(Base):
    """
    盘点单行下的 lot 快照参考明细

    设计原则：
    - 不作为盘点主行业务锚点
    - 只保存 snapshot_at 时点该商品的 lot 分布
    - 供页面参考与后续过账分摊使用
    """

    __tablename__ = "count_doc_line_lot_snapshots"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)

    line_id: Mapped[int] = mapped_column(
        sa.Integer,
        sa.ForeignKey(
            "count_doc_lines.id",
            name="fk_count_doc_line_lot_snapshots_line",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    lot_id: Mapped[int] = mapped_column(
        sa.Integer,
        sa.ForeignKey(
            "lots.id",
            name="fk_count_doc_line_lot_snapshots_lot",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    lot_code_snapshot: Mapped[Optional[str]] = mapped_column(sa.String(64), nullable=True)
    snapshot_qty_base: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )

    line: Mapped["CountDocLine"] = relationship(
        "CountDocLine",
        back_populates="lot_snapshots",
        lazy="selectin",
    )

    __table_args__ = (
        sa.UniqueConstraint(
            "line_id",
            "lot_id",
            name="uq_count_doc_line_lot_snapshots_line_lot",
        ),
        sa.CheckConstraint(
            "snapshot_qty_base >= 0",
            name="ck_count_doc_line_lot_snapshots_snapshot_qty_base_nonneg",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<CountDocLineLotSnapshot id={self.id} line_id={self.line_id} "
            f"lot_id={self.lot_id} snapshot_qty_base={self.snapshot_qty_base}>"
        )


__all__ = [
    "CountDoc",
    "CountDocLine",
    "CountDocLineLotSnapshot",
]
