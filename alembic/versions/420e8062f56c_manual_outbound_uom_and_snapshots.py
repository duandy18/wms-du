"""manual_outbound_uom_and_snapshots

Revision ID: 420e8062f56c
Revises: d77c6eba9c7e
Create Date: 2026-04-20 12:10:17.630567

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "420e8062f56c"
down_revision: Union[str, Sequence[str], None] = "d77c6eba9c7e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) docs：去掉来源层不再需要的字段
    op.drop_column("manual_outbound_docs", "recipient_type")
    op.drop_column("manual_outbound_docs", "recipient_note")

    # 2) lines：增加包装单位与展示快照
    op.add_column(
        "manual_outbound_lines",
        sa.Column("item_uom_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "manual_outbound_lines",
        sa.Column("item_name_snapshot", sa.Text(), nullable=True),
    )
    op.add_column(
        "manual_outbound_lines",
        sa.Column("item_spec_snapshot", sa.Text(), nullable=True),
    )
    op.add_column(
        "manual_outbound_lines",
        sa.Column("uom_name_snapshot", sa.Text(), nullable=True),
    )

    # 3) 用 item 的 outbound 默认包装 / base 包装回填历史数据
    op.execute(
        """
        UPDATE manual_outbound_lines AS l
        SET
          item_uom_id = src.item_uom_id,
          item_name_snapshot = src.item_name_snapshot,
          item_spec_snapshot = src.item_spec_snapshot,
          uom_name_snapshot = src.uom_name_snapshot
        FROM (
          SELECT
            l2.id AS line_id,
            iu.id AS item_uom_id,
            i.name AS item_name_snapshot,
            i.spec AS item_spec_snapshot,
            COALESCE(iu.display_name, iu.uom) AS uom_name_snapshot
          FROM manual_outbound_lines AS l2
          JOIN items AS i
            ON i.id = l2.item_id
          JOIN LATERAL (
            SELECT
              id,
              uom,
              display_name
            FROM item_uoms
            WHERE item_id = l2.item_id
            ORDER BY
              is_outbound_default DESC,
              is_base DESC,
              id ASC
            LIMIT 1
          ) AS iu
            ON TRUE
        ) AS src
        WHERE src.line_id = l.id
        """
    )

    # 4) 守护：若仍有未回填行，直接失败，避免半吊子迁移
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1
            FROM manual_outbound_lines
            WHERE item_uom_id IS NULL
          ) THEN
            RAISE EXCEPTION
              'manual_outbound_lines.item_uom_id backfill failed: some rows have no item_uom';
          END IF;
        END
        $$;
        """
    )

    op.alter_column(
        "manual_outbound_lines",
        "item_uom_id",
        existing_type=sa.BigInteger(),
        nullable=False,
    )

    op.create_foreign_key(
        "fk_manual_outbound_lines_item_uom_id",
        "manual_outbound_lines",
        "item_uoms",
        ["item_uom_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_manual_outbound_lines_item_uom_id",
        "manual_outbound_lines",
        ["item_uom_id"],
        unique=False,
    )

    # 5) 行备注不再保留
    op.drop_column("manual_outbound_lines", "remark")


def downgrade() -> None:
    # 1) 恢复行备注
    op.add_column(
        "manual_outbound_lines",
        sa.Column("remark", sa.Text(), nullable=True),
    )

    # 2) 去掉包装单位 FK / 索引
    op.drop_index(
        "ix_manual_outbound_lines_item_uom_id",
        table_name="manual_outbound_lines",
    )
    op.drop_constraint(
        "fk_manual_outbound_lines_item_uom_id",
        "manual_outbound_lines",
        type_="foreignkey",
    )

    # 3) 删除新增的行字段
    op.drop_column("manual_outbound_lines", "uom_name_snapshot")
    op.drop_column("manual_outbound_lines", "item_spec_snapshot")
    op.drop_column("manual_outbound_lines", "item_name_snapshot")
    op.drop_column("manual_outbound_lines", "item_uom_id")

    # 4) 恢复 docs 上的旧字段
    op.add_column(
        "manual_outbound_docs",
        sa.Column("recipient_note", sa.Text(), nullable=True),
    )
    op.add_column(
        "manual_outbound_docs",
        sa.Column("recipient_type", sa.Text(), nullable=True),
    )
