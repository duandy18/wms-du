"""8a_items_add_shelf_life_fields

- 新增 items.shelf_life_value（INTEGER, 可空）
- 新增 items.shelf_life_unit（VARCHAR(16), 可空）
- 迁移已有 shelf_life_days 数据：非空则视为按天（DAY）
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cd7510535092'
down_revision: Union[str, Sequence[str], None] = 'b02bd3073ec0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add shelf_life_value + shelf_life_unit, migrate old data."""

    # 1) 新增列
    op.add_column(
        "items",
        sa.Column("shelf_life_value", sa.Integer(), nullable=True),
    )
    op.add_column(
        "items",
        sa.Column("shelf_life_unit", sa.String(length=16), nullable=True),
    )

    # 2) 用已有 shelf_life_days 填充新字段
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE items
            SET shelf_life_value = shelf_life_days,
                shelf_life_unit = 'DAY'
            WHERE shelf_life_days IS NOT NULL
            """
        )
    )


def downgrade() -> None:
    """Remove newly added columns."""
    op.drop_column("items", "shelf_life_unit")
    op.drop_column("items", "shelf_life_value")
