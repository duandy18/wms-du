"""inventory_adjustment_rebuild_count_doc_lines_item_anchor_and_add_lot_snapshots

Revision ID: 11c7f84c84b0
Revises: 265fe9d55bbd
Create Date: 2026-04-22 15:44:41.216157

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "11c7f84c84b0"
down_revision: Union[str, Sequence[str], None] = "265fe9d55bbd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    conn = op.get_bind()

    # ------------------------------------------------------------------
    # 0) 保护：本迁移会重建 count_doc_lines。
    #    若已有真实数据，必须停下来做数据迁移，不能直接 drop/recreate。
    # ------------------------------------------------------------------
    line_rows = conn.execute(sa.text("SELECT COUNT(*) FROM count_doc_lines")).scalar()
    if int(line_rows or 0) > 0:
        raise RuntimeError(
            "count_doc_lines contains data; this migration expects empty table and rebuilds line schema."
        )

    # ------------------------------------------------------------------
    # 1) count_docs.status 扩为 5 态：增加 FROZEN
    # ------------------------------------------------------------------
    op.drop_constraint(
        "ck_count_docs_status",
        "count_docs",
        type_="check",
    )
    op.create_check_constraint(
        "ck_count_docs_status",
        "count_docs",
        "status IN ('DRAFT', 'FROZEN', 'COUNTED', 'POSTED', 'VOIDED')",
    )

    # ------------------------------------------------------------------
    # 2) 重建 count_doc_lines：
    #    从 lot 主锚点 -> item 主锚点
    # ------------------------------------------------------------------
    op.drop_table("count_doc_lines")

    op.create_table(
        "count_doc_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("doc_id", sa.Integer(), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),

        sa.Column("item_name_snapshot", sa.String(length=255), nullable=True),
        sa.Column("item_spec_snapshot", sa.String(length=255), nullable=True),

        sa.Column("snapshot_qty_base", sa.Integer(), nullable=False),

        sa.Column("counted_item_uom_id", sa.Integer(), nullable=True),
        sa.Column("counted_uom_name_snapshot", sa.String(length=64), nullable=True),
        sa.Column("counted_ratio_to_base_snapshot", sa.Integer(), nullable=True),
        sa.Column("counted_qty_input", sa.Integer(), nullable=True),

        sa.Column("counted_qty_base", sa.Integer(), nullable=True),
        sa.Column("diff_qty_base", sa.Integer(), nullable=True),

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
            ["counted_item_uom_id", "item_id"],
            ["item_uoms.id", "item_uoms.item_id"],
            name="fk_count_doc_lines_counted_item_uom_pair",
            ondelete="RESTRICT",
        ),

        sa.PrimaryKeyConstraint("id", name="pk_count_doc_lines"),
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
        "ix_count_doc_lines_counted_item_uom_id",
        "count_doc_lines",
        ["counted_item_uom_id"],
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

    # ------------------------------------------------------------------
    # 3) 新建 lot 快照参考子表
    # ------------------------------------------------------------------
    op.create_table(
        "count_doc_line_lot_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("line_id", sa.Integer(), nullable=False),
        sa.Column("lot_id", sa.Integer(), nullable=False),
        sa.Column("lot_code_snapshot", sa.String(length=64), nullable=True),
        sa.Column("snapshot_qty_base", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),

        sa.ForeignKeyConstraint(
            ["line_id"],
            ["count_doc_lines.id"],
            name="fk_count_doc_line_lot_snapshots_line",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["lot_id"],
            ["lots.id"],
            name="fk_count_doc_line_lot_snapshots_lot",
            ondelete="RESTRICT",
        ),

        sa.PrimaryKeyConstraint("id", name="pk_count_doc_line_lot_snapshots"),
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

    op.create_index(
        "ix_count_doc_line_lot_snapshots_line_id",
        "count_doc_line_lot_snapshots",
        ["line_id"],
        unique=False,
    )
    op.create_index(
        "ix_count_doc_line_lot_snapshots_lot_id",
        "count_doc_line_lot_snapshots",
        ["lot_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""

    conn = op.get_bind()

    # ------------------------------------------------------------------
    # 0) 保护：降级会重建 count_doc_lines 并删除子表。
    #    若已有数据，不允许直接回退，避免误删业务数据。
    # ------------------------------------------------------------------
    lot_rows = conn.execute(
        sa.text("SELECT COUNT(*) FROM count_doc_line_lot_snapshots")
    ).scalar()
    if int(lot_rows or 0) > 0:
        raise RuntimeError(
            "count_doc_line_lot_snapshots contains data; downgrade would drop it."
        )

    line_rows = conn.execute(sa.text("SELECT COUNT(*) FROM count_doc_lines")).scalar()
    if int(line_rows or 0) > 0:
        raise RuntimeError(
            "count_doc_lines contains data; downgrade would rebuild legacy schema and lose data."
        )

    frozen_rows = conn.execute(
        sa.text("SELECT COUNT(*) FROM count_docs WHERE status = 'FROZEN'")
    ).scalar()
    if int(frozen_rows or 0) > 0:
        raise RuntimeError(
            "count_docs contains FROZEN rows; clear them before downgrade."
        )

    # ------------------------------------------------------------------
    # 1) 回滚子表
    # ------------------------------------------------------------------
    op.drop_table("count_doc_line_lot_snapshots")

    # ------------------------------------------------------------------
    # 2) 回滚主行表：恢复到 lot 主锚点版本
    # ------------------------------------------------------------------
    op.drop_table("count_doc_lines")

    op.create_table(
        "count_doc_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("doc_id", sa.Integer(), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("lot_id", sa.Integer(), nullable=False),
        sa.Column("lot_code_snapshot", sa.String(length=64), nullable=True),

        sa.Column("item_name_snapshot", sa.String(length=255), nullable=True),
        sa.Column("item_spec_snapshot", sa.String(length=255), nullable=True),

        sa.Column("snapshot_qty_base", sa.Integer(), nullable=False),

        sa.Column("counted_item_uom_id", sa.Integer(), nullable=True),
        sa.Column("counted_uom_name_snapshot", sa.String(length=64), nullable=True),
        sa.Column("counted_ratio_to_base_snapshot", sa.Integer(), nullable=True),
        sa.Column("counted_qty_input", sa.Integer(), nullable=True),

        sa.Column("counted_qty_base", sa.Integer(), nullable=True),
        sa.Column("diff_qty_base", sa.Integer(), nullable=True),

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
        sa.ForeignKeyConstraint(
            ["counted_item_uom_id"],
            ["item_uoms.id"],
            name="fk_count_doc_lines_counted_item_uom",
            ondelete="RESTRICT",
        ),

        sa.PrimaryKeyConstraint("id", name="pk_count_doc_lines"),
        sa.UniqueConstraint("doc_id", "line_no", name="uq_count_doc_lines_doc_line"),

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
        "ix_count_doc_lines_counted_item_uom_id",
        "count_doc_lines",
        ["counted_item_uom_id"],
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

    # ------------------------------------------------------------------
    # 3) count_docs.status 回滚到 4 态
    # ------------------------------------------------------------------
    op.drop_constraint(
        "ck_count_docs_status",
        "count_docs",
        type_="check",
    )
    op.create_check_constraint(
        "ck_count_docs_status",
        "count_docs",
        "status IN ('DRAFT', 'COUNTED', 'POSTED', 'VOIDED')",
    )
