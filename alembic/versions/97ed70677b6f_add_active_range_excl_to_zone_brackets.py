"""add_active_range_excl_to_zone_brackets

Revision ID: 97ed70677b6f
Revises: 45fdd2438bca
Create Date: 2026-03-06 11:42:50.986618

目标：
- 新增命中路径索引 (zone_id, active, min_kg)
- 为 active brackets 添加区间不重叠 exclusion constraint
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision: str = "97ed70677b6f"
down_revision: Union[str, Sequence[str], None] = "45fdd2438bca"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "shipping_provider_zone_brackets"
IDX = "ix_sp_zone_brackets_zone_active_min"
EXCL = "excl_spzb_active_zone_weight_range_no_overlap"


def upgrade() -> None:
    # 1️⃣ GiST "=" 运算需要 btree_gist
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    # 2️⃣ 命中路径索引
    op.create_index(
        IDX,
        TABLE,
        ["zone_id", "active", "min_kg"],
        unique=False,
    )

    # 3️⃣ active rows 区间不重叠
    op.execute(
        f"""
        ALTER TABLE {TABLE}
        ADD CONSTRAINT {EXCL}
        EXCLUDE USING gist (
            zone_id WITH =,
            numrange(min_kg, max_kg, '[)') WITH &&
        )
        WHERE (active)
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        ALTER TABLE {TABLE}
        DROP CONSTRAINT IF EXISTS {EXCL}
        """
    )

    op.drop_index(IDX, table_name=TABLE)
