"""backfill lots production_date from ledger and receipt

Revision ID: 24ddc21b01e6
Revises: f054e01c63b1
Create Date: 2026-04-11 15:10:00.676420

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "24ddc21b01e6"
down_revision: Union[str, Sequence[str], None] = "f054e01c63b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        sa.text(
            """
            WITH ledger_one AS (
                SELECT
                    g.lot_id,
                    MIN(g.production_date) AS pd,
                    COUNT(DISTINCT g.production_date) AS distinct_pd
                FROM stock_ledger AS g
                WHERE g.reason_canon = 'RECEIPT'
                  AND g.production_date IS NOT NULL
                GROUP BY g.lot_id
            ),
            receipt_one AS (
                SELECT
                    rl.lot_id,
                    MIN(rl.production_date) AS pd,
                    COUNT(DISTINCT rl.production_date) AS distinct_pd
                FROM inbound_receipt_lines AS rl
                WHERE rl.production_date IS NOT NULL
                GROUP BY rl.lot_id
            ),
            resolved AS (
                SELECT
                    l.id AS lot_id,
                    CASE
                        WHEN lo.distinct_pd = 1 AND COALESCE(ro.distinct_pd, 0) = 0 THEN lo.pd
                        WHEN ro.distinct_pd = 1 AND COALESCE(lo.distinct_pd, 0) = 0 THEN ro.pd
                        WHEN lo.distinct_pd = 1 AND ro.distinct_pd = 1 AND lo.pd = ro.pd THEN lo.pd
                        ELSE NULL
                    END AS candidate_pd
                FROM lots AS l
                LEFT JOIN ledger_one AS lo
                  ON lo.lot_id = l.id
                LEFT JOIN receipt_one AS ro
                  ON ro.lot_id = l.id
                WHERE l.item_expiry_policy_snapshot = 'REQUIRED'::expiry_policy
                  AND l.production_date IS NULL
            )
            UPDATE lots AS l
               SET production_date = r.candidate_pd
              FROM resolved AS r
             WHERE l.id = r.lot_id
               AND r.candidate_pd IS NOT NULL
            """
        )
    )


def downgrade() -> None:
    """Downgrade schema.

    Best-effort rollback for this backfill step only:
    only revert rows whose current production_date still matches the same
    uniquely-derived candidate from ledger / receipt sources.
    """
    op.execute(
        sa.text(
            """
            WITH ledger_one AS (
                SELECT
                    g.lot_id,
                    MIN(g.production_date) AS pd,
                    COUNT(DISTINCT g.production_date) AS distinct_pd
                FROM stock_ledger AS g
                WHERE g.reason_canon = 'RECEIPT'
                  AND g.production_date IS NOT NULL
                GROUP BY g.lot_id
            ),
            receipt_one AS (
                SELECT
                    rl.lot_id,
                    MIN(rl.production_date) AS pd,
                    COUNT(DISTINCT rl.production_date) AS distinct_pd
                FROM inbound_receipt_lines AS rl
                WHERE rl.production_date IS NOT NULL
                GROUP BY rl.lot_id
            ),
            resolved AS (
                SELECT
                    l.id AS lot_id,
                    CASE
                        WHEN lo.distinct_pd = 1 AND COALESCE(ro.distinct_pd, 0) = 0 THEN lo.pd
                        WHEN ro.distinct_pd = 1 AND COALESCE(lo.distinct_pd, 0) = 0 THEN ro.pd
                        WHEN lo.distinct_pd = 1 AND ro.distinct_pd = 1 AND lo.pd = ro.pd THEN lo.pd
                        ELSE NULL
                    END AS candidate_pd
                FROM lots AS l
                LEFT JOIN ledger_one AS lo
                  ON lo.lot_id = l.id
                LEFT JOIN receipt_one AS ro
                  ON ro.lot_id = l.id
                WHERE l.item_expiry_policy_snapshot = 'REQUIRED'::expiry_policy
                  AND l.production_date IS NOT NULL
            )
            UPDATE lots AS l
               SET production_date = NULL
              FROM resolved AS r
             WHERE l.id = r.lot_id
               AND r.candidate_pd IS NOT NULL
               AND l.production_date = r.candidate_pd
            """
        )
    )
