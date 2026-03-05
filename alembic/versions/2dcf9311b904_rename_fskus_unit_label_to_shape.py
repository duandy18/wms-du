"""rename fskus.unit_label to shape

Revision ID: 2dcf9311b904
Revises: de32cf47e987
Create Date: 2026-02-06 18:02:25.889096
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2dcf9311b904"
down_revision: Union[str, Sequence[str], None] = "de32cf47e987"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) 列重命名：unit_label -> shape
    op.alter_column("fskus", "unit_label", new_column_name="shape")

    # 2) 类型收敛：varchar(50) -> varchar(20)
    op.alter_column(
        "fskus",
        "shape",
        existing_type=sa.String(length=50),
        type_=sa.String(length=20),
        nullable=True,
    )

    # 3) 清洗历史数据：
    #    - NULL / 旧值（如“件”）统一收敛为 bundle
    op.execute(sa.text("UPDATE fskus SET shape = 'bundle' WHERE shape IS NULL"))
    op.execute(sa.text("UPDATE fskus SET shape = 'bundle' WHERE shape NOT IN ('single','bundle')"))

    # 4) 约束：NOT NULL + DEFAULT + CHECK
    op.alter_column("fskus", "shape", nullable=False, server_default="bundle")
    op.create_check_constraint(
        "ck_fskus_shape",
        "fskus",
        "shape IN ('single','bundle')",
    )


def downgrade() -> None:
    # 回滚：shape -> unit_label（注意：原“单位”语义已不可恢复，这是设计决定）
    op.drop_constraint("ck_fskus_shape", "fskus", type_="check")

    op.alter_column("fskus", "shape", nullable=True, server_default=None)

    op.alter_column(
        "fskus",
        "shape",
        existing_type=sa.String(length=20),
        type_=sa.String(length=50),
        nullable=True,
    )

    op.alter_column("fskus", "shape", new_column_name="unit_label")
