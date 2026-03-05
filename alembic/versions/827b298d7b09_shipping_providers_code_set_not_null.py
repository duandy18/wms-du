"""shipping_providers.code set NOT NULL

Revision ID: 827b298d7b09
Revises: ff30b9b8423c
Create Date: 2026-03-03 17:36:00.285156
"""

from typing import Sequence, Union
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "827b298d7b09"
down_revision: Union[str, Sequence[str], None] = "ff30b9b8423c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 在设置 NOT NULL 之前，确保没有 NULL 数据
    # 如果已经确认没有 NULL，这条 UPDATE 不会产生影响
    op.execute(
        """
        UPDATE shipping_providers
        SET code = 'OUTLET-' || id
        WHERE code IS NULL;
        """
    )

    op.execute(
        """
        ALTER TABLE shipping_providers
        ALTER COLUMN code SET NOT NULL;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE shipping_providers
        ALTER COLUMN code DROP NOT NULL;
        """
    )
