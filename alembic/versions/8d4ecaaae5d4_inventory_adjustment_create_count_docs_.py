"""inventory_adjustment_create_count_docs_and_count_doc_lines

Revision ID: 8d4ecaaae5d4
Revises: 3ac042b64340
Create Date: 2026-04-22 13:44:16.452810

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8d4ecaaae5d4"
down_revision: Union[str, Sequence[str], None] = "3ac042b64340"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # ------------------------------------------------------------------
    # 1) 盘点单头：count_docs
    # ------------------------------------------------------------------
    op.create_table(
        "count_docs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("count_no", sa.String(length=64), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="DRAFT",
        ),
        sa.Column("posted_event_id", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("remark", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("counted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["warehouse_id"],
            ["warehouses.id"],
            name="fk_count_docs_warehouse",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["posted_event_id"],
            ["wms_events.id"],
            name="fk_count_docs_posted_event",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_count_docs_created_by",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_count_docs"),
        sa.UniqueConstraint("count_no", name="uq_count_docs_count_no"),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'COUNTED', 'POSTED', 'VOIDED')",
            name="ck_count_docs_status",
        ),
    )

    op.create_index(
        "ix_count_docs_status",
        "count_docs",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_count_docs_warehouse_snapshot_at",
        "count_docs",
        ["warehouse_id", "snapshot_at"],
        unique=False,
    )
    op.create_index(
        "ix_count_docs_posted_event_id",
        "count_docs",
        ["posted_event_id"],
        unique=False,
    )

    # ------------------------------------------------------------------
    # 2) 盘点单明细：count_doc_lines
    #
    # 设计原则：
    # - lot-world：结构锚点用 lot_id
    # - lot_code_snapshot 只做展示快照
    # - snapshot_qty 为冻结时点库存
    # - counted_qty 为人工实盘数量，可先为空
    # - diff_qty 由后端维护；当 counted_qty 为空时必须为空
    # ------------------------------------------------------------------
    op.create_table(
        "count_doc_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("doc_id", sa.Integer(), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("lot_id", sa.Integer(), nullable=False),
        sa.Column("lot_code_snapshot", sa.String(length=64), nullable=True),
        sa.Column("snapshot_qty", sa.Integer(), nullable=False),
        sa.Column("counted_qty", sa.Integer(), nullable=True),
        sa.Column("diff_qty", sa.Integer(), nullable=True),
        sa.Column("reason_code", sa.String(length=32), nullable=True),
        sa.Column("disposition", sa.String(length=32), nullable=True),
        sa.Column("remark", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["doc_id"],
            ["count_docs.id"],
            name="fk_count_doc_lines_doc",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["items.id"],
            name="fk_count_doc_lines_item",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["lot_id"],
            ["lots.id"],
            name="fk_count_doc_lines_lot",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_count_doc_lines"),
        sa.UniqueConstraint(
            "doc_id",
            "line_no",
            name="uq_count_doc_lines_doc_line",
        ),
        sa.CheckConstraint(
            "line_no >= 1",
            name="ck_count_doc_lines_line_no_positive",
        ),
        sa.CheckConstraint(
            "snapshot_qty >= 0",
            name="ck_count_doc_lines_snapshot_qty_nonneg",
        ),
        sa.CheckConstraint(
            "counted_qty IS NULL OR counted_qty >= 0",
            name="ck_count_doc_lines_counted_qty_nonneg",
        ),
        sa.CheckConstraint(
            "("
            "  (counted_qty IS NULL AND diff_qty IS NULL)"
            "  OR"
            "  (counted_qty IS NOT NULL AND diff_qty = counted_qty - snapshot_qty)"
            ")",
            name="ck_count_doc_lines_diff_consistent",
        ),
    )

    op.create_index(
        "ix_count_doc_lines_doc_id",
        "count_doc_lines",
        ["doc_id"],
        unique=False,
    )
    op.create_index(
        "ix_count_doc_lines_item_id",
        "count_doc_lines",
        ["item_id"],
        unique=False,
    )
    op.create_index(
        "ix_count_doc_lines_lot_id",
        "count_doc_lines",
        ["lot_id"],
        unique=False,
    )
    op.create_index(
        "ix_count_doc_lines_reason_code",
        "count_doc_lines",
        ["reason_code"],
        unique=False,
    )
    op.create_index(
        "ix_count_doc_lines_disposition",
        "count_doc_lines",
        ["disposition"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_table("count_doc_lines")
    op.drop_table("count_docs")
