"""p43_add_trace_id_to_reservations

Revision ID: 629edd10564d
Revises: 6b6ad93cf221
Create Date: 2025-11-16 09:23:29.716401
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "629edd10564d"
down_revision: Union[str, Sequence[str], None] = "6b6ad93cf221"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """给 reservations 补充 trace_id 列并回填。"""

    # 1) 增加 trace_id 列（可空，方便渐进接入）
    op.add_column(
        "reservations",
        sa.Column("trace_id", sa.String(length=64), nullable=True),
    )

    # 2) 回填现有数据：把 ref 的值同步到 trace_id（只填空值）
    op.execute(
        """
        UPDATE reservations
           SET trace_id = ref
         WHERE trace_id IS NULL
        """
    )

    # 3) 建索引，便于按 trace_id 查询
    op.create_index(
        "ix_reservations_trace_id",
        "reservations",
        ["trace_id"],
    )


def downgrade() -> None:
    """回滚 trace_id 列和索引。"""

    op.drop_index("ix_reservations_trace_id", table_name="reservations")
    op.drop_column("reservations", "trace_id")
