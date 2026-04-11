"""delete duplicate required lots test data

Revision ID: 846b07d478c8
Revises: 24ddc21b01e6
Create Date: 2026-04-11 15:20:22.543878

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "846b07d478c8"
down_revision: Union[str, Sequence[str], None] = "24ddc21b01e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    测试数据清理策略：
    - 对 REQUIRED 商品下，同 (warehouse_id, item_id, production_date) 的重复 lots，
      保留最小 id 作为 canonical_lot_id
    - 直接删除其它 duplicate lots 及其挂载的测试数据
    - 不做 merge / repoint
    """
    bind = op.get_bind()

    # 先删引用表，后删 lots
    bind.execute(
        sa.text(
            """
            WITH dup AS (
                SELECT
                    id AS old_lot_id,
                    MIN(id) OVER (PARTITION BY warehouse_id, item_id, production_date) AS canonical_lot_id
                FROM lots
                WHERE item_expiry_policy_snapshot = 'REQUIRED'::expiry_policy
                  AND production_date IS NOT NULL
            ),
            doomed AS (
                SELECT old_lot_id
                FROM dup
                WHERE old_lot_id <> canonical_lot_id
            )
            DELETE FROM stock_ledger
            WHERE lot_id IN (SELECT old_lot_id FROM doomed)
            """
        )
    )

    bind.execute(
        sa.text(
            """
            WITH dup AS (
                SELECT
                    id AS old_lot_id,
                    MIN(id) OVER (PARTITION BY warehouse_id, item_id, production_date) AS canonical_lot_id
                FROM lots
                WHERE item_expiry_policy_snapshot = 'REQUIRED'::expiry_policy
                  AND production_date IS NOT NULL
            ),
            doomed AS (
                SELECT old_lot_id
                FROM dup
                WHERE old_lot_id <> canonical_lot_id
            )
            DELETE FROM stocks_lot
            WHERE lot_id IN (SELECT old_lot_id FROM doomed)
            """
        )
    )

    bind.execute(
        sa.text(
            """
            WITH dup AS (
                SELECT
                    id AS old_lot_id,
                    MIN(id) OVER (PARTITION BY warehouse_id, item_id, production_date) AS canonical_lot_id
                FROM lots
                WHERE item_expiry_policy_snapshot = 'REQUIRED'::expiry_policy
                  AND production_date IS NOT NULL
            ),
            doomed AS (
                SELECT old_lot_id
                FROM dup
                WHERE old_lot_id <> canonical_lot_id
            )
            DELETE FROM stock_snapshots
            WHERE lot_id IN (SELECT old_lot_id FROM doomed)
            """
        )
    )

    bind.execute(
        sa.text(
            """
            WITH dup AS (
                SELECT
                    id AS old_lot_id,
                    MIN(id) OVER (PARTITION BY warehouse_id, item_id, production_date) AS canonical_lot_id
                FROM lots
                WHERE item_expiry_policy_snapshot = 'REQUIRED'::expiry_policy
                  AND production_date IS NOT NULL
            ),
            doomed AS (
                SELECT old_lot_id
                FROM dup
                WHERE old_lot_id <> canonical_lot_id
            )
            DELETE FROM inbound_receipt_lines
            WHERE lot_id IN (SELECT old_lot_id FROM doomed)
            """
        )
    )

    bind.execute(
        sa.text(
            """
            WITH dup AS (
                SELECT
                    id AS old_lot_id,
                    MIN(id) OVER (PARTITION BY warehouse_id, item_id, production_date) AS canonical_lot_id
                FROM lots
                WHERE item_expiry_policy_snapshot = 'REQUIRED'::expiry_policy
                  AND production_date IS NOT NULL
            ),
            doomed AS (
                SELECT old_lot_id
                FROM dup
                WHERE old_lot_id <> canonical_lot_id
            )
            DELETE FROM lots
            WHERE id IN (SELECT old_lot_id FROM doomed)
            """
        )
    )


def downgrade() -> None:
    """Downgrade schema.

    这是测试数据清理迁移，删除不可逆。
    """
    raise NotImplementedError("irreversible test-data cleanup migration")
