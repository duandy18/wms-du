"""shipping_records: switch tracking unique from carrier_code to provider_id

Revision ID: 70144e0014e5
Revises: 9b2e6b38fc8b
Create Date: 2026-03-05 18:29:33.016857
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "70144e0014e5"
down_revision: Union[str, Sequence[str], None] = "9b2e6b38fc8b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    将运单唯一约束从
        (carrier_code, tracking_no)
    切换为
        (shipping_provider_id, tracking_no)
    """

    # 删除旧索引
    op.execute(
        """
        DROP INDEX IF EXISTS uq_shipping_records_carrier_tracking_notnull;
        """
    )

    # 创建新索引
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_shipping_records_provider_tracking_notnull
        ON shipping_records (shipping_provider_id, tracking_no)
        WHERE tracking_no IS NOT NULL;
        """
    )


def downgrade() -> None:
    """
    回滚：恢复旧唯一约束
    """

    op.execute(
        """
        DROP INDEX IF EXISTS uq_shipping_records_provider_tracking_notnull;
        """
    )

    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_shipping_records_carrier_tracking_notnull
        ON shipping_records (carrier_code, tracking_no)
        WHERE tracking_no IS NOT NULL;
        """
    )
