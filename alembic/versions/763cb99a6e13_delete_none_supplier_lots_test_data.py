"""delete none supplier lots test data

Revision ID: 763cb99a6e13
Revises: 846b07d478c8
Create Date: 2026-04-11 15:23:56.410027

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "763cb99a6e13"
down_revision: Union[str, Sequence[str], None] = "846b07d478c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    测试数据清理：
    - 删除所有 NONE 商品下的 SUPPLIER lots
    - 以及这些 lot 挂载的 stock_ledger / stocks_lot / stock_snapshots / inbound_receipt_lines
    - 不做 merge / repoint
    """
    bind = op.get_bind()

    bind.execute(
        sa.text(
            """
            WITH doomed AS (
                SELECT id AS lot_id
                FROM lots
                WHERE item_expiry_policy_snapshot = 'NONE'::expiry_policy
                  AND lot_code_source = 'SUPPLIER'
            )
            DELETE FROM stock_ledger
            WHERE lot_id IN (SELECT lot_id FROM doomed)
            """
        )
    )

    bind.execute(
        sa.text(
            """
            WITH doomed AS (
                SELECT id AS lot_id
                FROM lots
                WHERE item_expiry_policy_snapshot = 'NONE'::expiry_policy
                  AND lot_code_source = 'SUPPLIER'
            )
            DELETE FROM stocks_lot
            WHERE lot_id IN (SELECT lot_id FROM doomed)
            """
        )
    )

    bind.execute(
        sa.text(
            """
            WITH doomed AS (
                SELECT id AS lot_id
                FROM lots
                WHERE item_expiry_policy_snapshot = 'NONE'::expiry_policy
                  AND lot_code_source = 'SUPPLIER'
            )
            DELETE FROM stock_snapshots
            WHERE lot_id IN (SELECT lot_id FROM doomed)
            """
        )
    )

    bind.execute(
        sa.text(
            """
            WITH doomed AS (
                SELECT id AS lot_id
                FROM lots
                WHERE item_expiry_policy_snapshot = 'NONE'::expiry_policy
                  AND lot_code_source = 'SUPPLIER'
            )
            DELETE FROM inbound_receipt_lines
            WHERE lot_id IN (SELECT lot_id FROM doomed)
            """
        )
    )

    bind.execute(
        sa.text(
            """
            DELETE FROM lots
            WHERE item_expiry_policy_snapshot = 'NONE'::expiry_policy
              AND lot_code_source = 'SUPPLIER'
            """
        )
    )


def downgrade() -> None:
    """Downgrade schema.

    测试数据删除不可逆。
    """
    raise NotImplementedError("irreversible test-data cleanup migration")
