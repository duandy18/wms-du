"""wms_lot_backfill_expiry_date_from_receipt_and_ledger

Revision ID: 3bd2a92976ba
Revises: 6176a3ab53ba
Create Date: 2026-04-11 19:52:50.909587

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "3bd2a92976ba"
down_revision: Union[str, Sequence[str], None] = "6176a3ab53ba"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()

    # 1) receipt line 内部：同一 lot 不能出现多个不同 expiry_date
    line_conflicts = conn.execute(
        sa.text(
            """
            WITH target_lots AS (
                SELECT id
                FROM lots
                WHERE item_expiry_policy_snapshot = 'REQUIRED'
                  AND lot_code_source = 'SUPPLIER'
            ),
            conflicts AS (
                SELECT rl.lot_id
                FROM inbound_receipt_lines rl
                JOIN target_lots tl
                  ON tl.id = rl.lot_id
                WHERE rl.expiry_date IS NOT NULL
                GROUP BY rl.lot_id
                HAVING COUNT(DISTINCT rl.expiry_date) > 1
            )
            SELECT COUNT(*) FROM conflicts
            """
        )
    ).scalar_one()
    if int(line_conflicts or 0) > 0:
        raise RuntimeError(
            "wms_lot_backfill_expiry_date_from_receipt_and_ledger: "
            f"found {int(line_conflicts)} lots with conflicting expiry_date in inbound_receipt_lines"
        )

    # 2) ledger 内部：同一 lot 的 RECEIPT 事件不能出现多个不同 expiry_date
    ledger_conflicts = conn.execute(
        sa.text(
            """
            WITH target_lots AS (
                SELECT id
                FROM lots
                WHERE item_expiry_policy_snapshot = 'REQUIRED'
                  AND lot_code_source = 'SUPPLIER'
            ),
            conflicts AS (
                SELECT sl.lot_id
                FROM stock_ledger sl
                JOIN target_lots tl
                  ON tl.id = sl.lot_id
                WHERE sl.reason_canon = 'RECEIPT'
                  AND sl.expiry_date IS NOT NULL
                GROUP BY sl.lot_id
                HAVING COUNT(DISTINCT sl.expiry_date) > 1
            )
            SELECT COUNT(*) FROM conflicts
            """
        )
    ).scalar_one()
    if int(ledger_conflicts or 0) > 0:
        raise RuntimeError(
            "wms_lot_backfill_expiry_date_from_receipt_and_ledger: "
            f"found {int(ledger_conflicts)} lots with conflicting expiry_date in stock_ledger(RECEIPT)"
        )

    # 3) line 与 ledger 若同时有值，不能互相打架
    cross_conflicts = conn.execute(
        sa.text(
            """
            WITH target_lots AS (
                SELECT id
                FROM lots
                WHERE item_expiry_policy_snapshot = 'REQUIRED'
                  AND lot_code_source = 'SUPPLIER'
            ),
            line_src AS (
                SELECT
                    rl.lot_id,
                    MIN(rl.expiry_date) AS expiry_date
                FROM inbound_receipt_lines rl
                JOIN target_lots tl
                  ON tl.id = rl.lot_id
                WHERE rl.expiry_date IS NOT NULL
                GROUP BY rl.lot_id
            ),
            ledger_src AS (
                SELECT
                    sl.lot_id,
                    MIN(sl.expiry_date) AS expiry_date
                FROM stock_ledger sl
                JOIN target_lots tl
                  ON tl.id = sl.lot_id
                WHERE sl.reason_canon = 'RECEIPT'
                  AND sl.expiry_date IS NOT NULL
                GROUP BY sl.lot_id
            ),
            conflicts AS (
                SELECT l.lot_id
                FROM line_src l
                JOIN ledger_src g
                  ON g.lot_id = l.lot_id
                WHERE l.expiry_date <> g.expiry_date
            )
            SELECT COUNT(*) FROM conflicts
            """
        )
    ).scalar_one()
    if int(cross_conflicts or 0) > 0:
        raise RuntimeError(
            "wms_lot_backfill_expiry_date_from_receipt_and_ledger: "
            f"found {int(cross_conflicts)} lots with line/ledger expiry_date mismatch"
        )

    # 4) 优先用 receipt line 回填
    conn.execute(
        sa.text(
            """
            WITH line_src AS (
                SELECT
                    rl.lot_id,
                    MIN(rl.expiry_date) AS expiry_date
                FROM inbound_receipt_lines rl
                JOIN lots l
                  ON l.id = rl.lot_id
                WHERE l.item_expiry_policy_snapshot = 'REQUIRED'
                  AND l.lot_code_source = 'SUPPLIER'
                  AND rl.expiry_date IS NOT NULL
                GROUP BY rl.lot_id
            )
            UPDATE lots l
               SET expiry_date = src.expiry_date
              FROM line_src src
             WHERE l.id = src.lot_id
               AND l.item_expiry_policy_snapshot = 'REQUIRED'
               AND l.lot_code_source = 'SUPPLIER'
               AND l.expiry_date IS NULL
               AND (l.production_date IS NULL OR src.expiry_date >= l.production_date)
            """
        )
    )

    # 5) 再用 RECEIPT ledger 兜底
    conn.execute(
        sa.text(
            """
            WITH ledger_src AS (
                SELECT
                    sl.lot_id,
                    MIN(sl.expiry_date) AS expiry_date
                FROM stock_ledger sl
                JOIN lots l
                  ON l.id = sl.lot_id
                WHERE l.item_expiry_policy_snapshot = 'REQUIRED'
                  AND l.lot_code_source = 'SUPPLIER'
                  AND sl.reason_canon = 'RECEIPT'
                  AND sl.expiry_date IS NOT NULL
                GROUP BY sl.lot_id
            )
            UPDATE lots l
               SET expiry_date = src.expiry_date
              FROM ledger_src src
             WHERE l.id = src.lot_id
               AND l.item_expiry_policy_snapshot = 'REQUIRED'
               AND l.lot_code_source = 'SUPPLIER'
               AND l.expiry_date IS NULL
               AND (l.production_date IS NULL OR src.expiry_date >= l.production_date)
            """
        )
    )


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()

    # best-effort rollback：
    # 仅清空 REQUIRED + SUPPLIER lots 上这一轮回填得到的 canonical expiry_date
    conn.execute(
        sa.text(
            """
            UPDATE lots
               SET expiry_date = NULL
             WHERE item_expiry_policy_snapshot = 'REQUIRED'
               AND lot_code_source = 'SUPPLIER'
            """
        )
    )
