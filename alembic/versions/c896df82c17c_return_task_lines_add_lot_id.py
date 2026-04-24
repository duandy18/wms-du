"""return task lines add lot_id structural anchor

Revision ID: c896df82c17c
Revises: a2ceea372e0e
Create Date: 2026-04-25 01:43:09.327580

Contract:
- return_task_lines.lot_id is the structural anchor for return-to-original-lot.
- return_task_lines.batch_code remains a display snapshot from lots.lot_code.
- Historical demo/UT rows that cannot be mapped back to current stock_ledger/lots are removed.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "c896df82c17c"
down_revision = "a2ceea372e0e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Remove historical/orphan return tasks that cannot be linked to current ledger facts.
    #
    # Terminal lot-world rule:
    #   return task creation must be driven by stock_ledger.ref and stock_ledger.lot_id.
    #
    # Any return_task without a matching stock_ledger.ref has no recoverable structural lot_id,
    # so it cannot be migrated into the new return_task_lines.lot_id NOT NULL contract.
    # This intentionally removes old demo/UT drift rows instead of introducing nullable fallback.
    op.execute(
        sa.text(
            """
            DELETE FROM return_tasks rt
             WHERE NOT EXISTS (
                     SELECT 1
                       FROM stock_ledger sl
                      WHERE sl.ref = rt.order_id
                   )
            """
        )
    )

    # 2) Add nullable first, then backfill, then enforce NOT NULL.
    op.add_column(
        "return_task_lines",
        sa.Column("lot_id", sa.Integer(), nullable=True),
    )

    # 3) Best-effort backfill for any real rows still present:
    #    order_id -> stock_ledger.ref, item/warehouse match, batch_code snapshot == lots.lot_code.
    #    Only unambiguous mappings are applied.
    op.execute(
        sa.text(
            """
            WITH mapped AS (
                SELECT
                    rtl.id AS return_task_line_id,
                    MIN(sl.lot_id)::int AS lot_id,
                    COUNT(DISTINCT sl.lot_id) AS lot_count
                FROM return_task_lines rtl
                JOIN return_tasks rt
                  ON rt.id = rtl.task_id
                JOIN stock_ledger sl
                  ON sl.ref = rt.order_id
                 AND sl.delta < 0
                 AND sl.reason IN ('SHIPMENT', 'OUTBOUND_SHIP')
                 AND sl.item_id = rtl.item_id
                 AND sl.warehouse_id = rt.warehouse_id
                JOIN lots lo
                  ON lo.id = sl.lot_id
                 AND lo.lot_code_source = 'SUPPLIER'
                 AND lo.lot_code = rtl.batch_code
                GROUP BY rtl.id
                HAVING COUNT(DISTINCT sl.lot_id) = 1
            )
            UPDATE return_task_lines rtl
               SET lot_id = mapped.lot_id
              FROM mapped
             WHERE rtl.id = mapped.return_task_line_id
               AND rtl.lot_id IS NULL
            """
        )
    )

    # 4) Fail loudly if any non-demo row cannot be migrated.
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                      FROM return_task_lines
                     WHERE lot_id IS NULL
                ) THEN
                    RAISE EXCEPTION
                        'return_task_lines.lot_id migration failed: NULL lot_id remains';
                END IF;
            END $$;
            """
        )
    )

    op.alter_column(
        "return_task_lines",
        "lot_id",
        existing_type=sa.Integer(),
        nullable=False,
    )

    op.create_index(
        "ix_return_task_lines_lot_id",
        "return_task_lines",
        ["lot_id"],
        unique=False,
    )

    op.create_foreign_key(
        "fk_return_task_lines_lot",
        "return_task_lines",
        "lots",
        ["lot_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.execute(
        sa.text(
            """
            COMMENT ON COLUMN return_task_lines.lot_id IS
            '结构锚点：退货回原批次对应的 lots.id，来自原出库 stock_ledger.lot_id'
            """
        )
    )
    op.execute(
        sa.text(
            """
            COMMENT ON COLUMN return_task_lines.batch_code IS
            '展示快照：来自原出库 lot 的 lots.lot_code；不参与结构锚点'
            """
        )
    )


def downgrade() -> None:
    op.drop_constraint("fk_return_task_lines_lot", "return_task_lines", type_="foreignkey")
    op.drop_index("ix_return_task_lines_lot_id", table_name="return_task_lines")
    op.drop_column("return_task_lines", "lot_id")

    op.execute(
        sa.text(
            """
            COMMENT ON COLUMN return_task_lines.batch_code IS
            '批次编码（系统自动回原批次：来自订单出库台账，必填；不允许人工补录）'
            """
        )
    )
