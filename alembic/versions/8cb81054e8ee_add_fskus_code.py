"""add fskus code

Revision ID: 8cb81054e8ee
Revises: 2dcf9311b904
Create Date: 2026-02-06 18:18:08.138712

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8cb81054e8ee"
down_revision: Union[str, Sequence[str], None] = "2dcf9311b904"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) 新增列：先允许 NULL，方便回填
    op.add_column("fskus", sa.Column("code", sa.String(length=64), nullable=True))

    # 2) 回填历史数据：生成稳定编码（FSKU-{id}）
    op.execute(sa.text("UPDATE fskus SET code = 'FSKU-' || id::text WHERE code IS NULL"))

    # 3) 设为 NOT NULL
    op.alter_column("fskus", "code", nullable=False)

    # 4) 全局唯一
    op.create_index("ux_fskus_code", "fskus", ["code"], unique=True)


def downgrade() -> None:
    op.drop_index("ux_fskus_code", table_name="fskus")
    op.drop_column("fskus", "code")
