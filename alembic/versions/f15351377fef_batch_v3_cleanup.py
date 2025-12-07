"""batch_v3_cleanup

Batch v3 Cleanup:
- Remove legacy columns:
    * qty
    * expire_at
    * mfg_date
    * shelf_life_days
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f15351377fef'
down_revision: Union[str, Sequence[str], None] = 'cd7510535092'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade Batch table to V3 schema."""

    with op.batch_alter_table("batches") as batch:

        # qty 已废弃，由 stocks.qty 为唯一真实库存来源
        batch.drop_column("qty")

        # expire_at = 旧字段（重复 expiry_date）
        batch.drop_column("expire_at")

        # mfg_date = manufacturing date（与 production_date 重复）
        batch.drop_column("mfg_date")

        # shelf_life_days 不应存储在 batch，属于 item 层
        batch.drop_column("shelf_life_days")


def downgrade() -> None:
    """Restore dropped columns."""

    with op.batch_alter_table("batches") as batch:
        batch.add_column(sa.Column("qty", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("expire_at", sa.Date(), nullable=True))
        batch.add_column(sa.Column("mfg_date", sa.Date(), nullable=True))
        batch.add_column(sa.Column("shelf_life_days", sa.Integer(), nullable=True))
