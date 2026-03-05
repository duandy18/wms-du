"""shipping_records: add shipping_provider_id

Revision ID: 15547a554fe0
Revises: e31f65b886d4
Create Date: 2026-03-03 19:11:47.211404
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "15547a554fe0"
down_revision: Union[str, Sequence[str], None] = "e31f65b886d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) 新增列（先允许 NULL，避免历史数据回填成本）
    op.execute(
        """
        ALTER TABLE shipping_records
        ADD COLUMN shipping_provider_id INTEGER;
        """
    )

    # 2) 外键（强链接到网点实体）
    op.execute(
        """
        ALTER TABLE shipping_records
        ADD CONSTRAINT fk_shipping_records_provider_id
        FOREIGN KEY (shipping_provider_id)
        REFERENCES shipping_providers(id)
        ON DELETE RESTRICT;
        """
    )

    # 3) 索引（按 provider 统计/对账/排障会用）
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_shipping_records_provider_id
        ON shipping_records (shipping_provider_id);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX IF EXISTS ix_shipping_records_provider_id;
        """
    )

    op.execute(
        """
        ALTER TABLE shipping_records
        DROP CONSTRAINT IF EXISTS fk_shipping_records_provider_id;
        """
    )

    op.execute(
        """
        ALTER TABLE shipping_records
        DROP COLUMN IF EXISTS shipping_provider_id;
        """
    )
