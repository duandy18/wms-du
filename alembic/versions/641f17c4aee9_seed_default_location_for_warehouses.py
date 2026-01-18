"""seed default location for warehouses

Revision ID: 641f17c4aee9
Revises: fbf9483e99b9
Create Date: 2026-01-17 18:13:16.818422

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "641f17c4aee9"
down_revision: Union[str, Sequence[str], None] = "fbf9483e99b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO locations (warehouse_id, name, code)
            SELECT w.id, '默认库位', 'DEFAULT'
              FROM warehouses w
             WHERE NOT EXISTS (
                SELECT 1
                  FROM locations l
                 WHERE l.warehouse_id = w.id
             );
            """
        )
    )


def downgrade() -> None:
    # 数据迁移不建议回滚，避免误删业务数据
    pass
