"""phase: lots lot_code_key + internal lot singleton

Revision ID: 00ab40d84c08
Revises: fdae32e49292
Create Date: 2026-03-04

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "00ab40d84c08"
down_revision: Union[str, Sequence[str], None] = "fdae32e49292"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:

    # ----------------------------------------------------
    # 1. 添加 lot_code_key
    # ----------------------------------------------------
    op.add_column(
        "lots",
        sa.Column("lot_code_key", sa.Text(), nullable=True),
    )

    # 归一化 lot_code
    op.execute(
        """
        UPDATE lots
           SET lot_code_key = upper(btrim(lot_code))
         WHERE lot_code IS NOT NULL
        """
    )

    # ----------------------------------------------------
    # 2. 合并 INTERNAL NULL-code lots
    # ----------------------------------------------------
    op.execute(
        """
        CREATE TEMP TABLE tmp_internal_lot_merge AS
        WITH grp AS (
            SELECT warehouse_id, item_id, MIN(id) AS keep_id
              FROM lots
             WHERE lot_code_source = 'INTERNAL'
               AND lot_code IS NULL
             GROUP BY warehouse_id, item_id
        )
        SELECT lo.id AS old_id,
               g.keep_id,
               lo.warehouse_id,
               lo.item_id
          FROM lots lo
          JOIN grp g
            ON lo.warehouse_id = g.warehouse_id
           AND lo.item_id = g.item_id
         WHERE lo.lot_code_source = 'INTERNAL'
           AND lo.lot_code IS NULL
           AND lo.id <> g.keep_id
        """
    )

    # stocks_lot
    op.execute(
        """
        UPDATE stocks_lot s
           SET lot_id = m.keep_id
          FROM tmp_internal_lot_merge m
         WHERE s.lot_id = m.old_id
           AND s.warehouse_id = m.warehouse_id
           AND s.item_id = m.item_id
        """
    )

    # stock_ledger
    op.execute(
        """
        UPDATE stock_ledger l
           SET lot_id = m.keep_id
          FROM tmp_internal_lot_merge m
         WHERE l.lot_id = m.old_id
           AND l.warehouse_id = m.warehouse_id
           AND l.item_id = m.item_id
        """
    )

    # stock_snapshots
    op.execute(
        """
        UPDATE stock_snapshots s
           SET lot_id = m.keep_id
          FROM tmp_internal_lot_merge m
         WHERE s.lot_id = m.old_id
           AND s.warehouse_id = m.warehouse_id
           AND s.item_id = m.item_id
        """
    )

    # inbound_receipt_lines
    op.execute(
        """
        UPDATE inbound_receipt_lines l
           SET lot_id = m.keep_id
          FROM tmp_internal_lot_merge m
         WHERE l.lot_id = m.old_id
           AND l.warehouse_id = m.warehouse_id
           AND l.item_id = m.item_id
        """
    )

    # 删除重复 INTERNAL lots
    op.execute(
        """
        DELETE FROM lots lo
         USING tmp_internal_lot_merge m
         WHERE lo.id = m.old_id
        """
    )

    op.execute("DROP TABLE tmp_internal_lot_merge")


    # ----------------------------------------------------
    # 3. 替换 supplier 唯一约束
    # ----------------------------------------------------
    op.drop_index("uq_lots_wh_item_lot_code", table_name="lots")

    op.create_index(
        "uq_lots_wh_item_lot_code_key",
        "lots",
        ["warehouse_id", "item_id", "lot_code_key"],
        unique=True,
        postgresql_where=sa.text("lot_code IS NOT NULL"),
    )


    # ----------------------------------------------------
    # 4. INTERNAL lot 单例约束
    # ----------------------------------------------------
    op.drop_index(
        "uq_lots_internal_wh_item_src_receipt_line",
        table_name="lots",
    )

    op.create_index(
        "uq_lots_internal_single_wh_item",
        "lots",
        ["warehouse_id", "item_id"],
        unique=True,
        postgresql_where=sa.text(
            "lot_code_source = 'INTERNAL' AND lot_code IS NULL"
        ),
    )


def downgrade() -> None:

    op.drop_index("uq_lots_internal_single_wh_item", table_name="lots")

    op.create_index(
        "uq_lots_internal_wh_item_src_receipt_line",
        "lots",
        ["warehouse_id", "item_id", "source_receipt_id", "source_line_no"],
        unique=True,
        postgresql_where=sa.text("lot_code_source = 'INTERNAL'"),
    )

    op.drop_index("uq_lots_wh_item_lot_code_key", table_name="lots")

    op.create_index(
        "uq_lots_wh_item_lot_code",
        "lots",
        ["warehouse_id", "item_id", "lot_code"],
        unique=True,
        postgresql_where=sa.text("lot_code IS NOT NULL"),
    )

    op.drop_column("lots", "lot_code_key")
