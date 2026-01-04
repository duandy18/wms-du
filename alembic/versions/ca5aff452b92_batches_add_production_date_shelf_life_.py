"""batches add production_date / shelf_life_days / created_at

Revision ID: 4e7a1b2c3d90
Revises: 996238f7ea7c
Create Date: 2025-11-09 22:18:00
"""
from typing import Sequence, Union
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4e7a1b2c3d90"
down_revision: Union[str, Sequence[str], None] = "996238f7ea7c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) 补列（若不存在）
    op.execute("ALTER TABLE batches ADD COLUMN IF NOT EXISTS production_date DATE")
    op.execute("ALTER TABLE batches ADD COLUMN IF NOT EXISTS shelf_life_days INTEGER")
    op.execute(
        "ALTER TABLE batches ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now()"
    )

    # 2) 可选回填（保持温和，不覆盖已有数据）
    op.execute(
        """
        UPDATE batches
           SET production_date = production_date
        """
    )
    op.execute(
        """
        UPDATE batches
           SET shelf_life_days = shelf_life_days
        """
    )


def downgrade() -> None:
    # 回滚（幂等删除）
    op.execute("ALTER TABLE batches DROP COLUMN IF EXISTS created_at")
    op.execute("ALTER TABLE batches DROP COLUMN IF EXISTS shelf_life_days")
    op.execute("ALTER TABLE batches DROP COLUMN IF EXISTS production_date")
