"""tms pricing template status drop active

Revision ID: b279c48eecab
Revises: 8958d9b251be
Create Date: 2026-03-21 13:17:24.746952

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b279c48eecab'
down_revision: Union[str, Sequence[str], None] = '8958d9b251be'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "shipping_provider_pricing_templates"
CK_NAME = "ck_sppt_status_valid"


def upgrade() -> None:
    """Upgrade schema."""

    # 1) 收口历史 active -> draft
    op.execute(
        sa.text(
            f"""
            UPDATE {TABLE}
               SET status = 'draft'
             WHERE status = 'active'
            """
        )
    )

    # 2) 删除旧约束
    op.drop_constraint(CK_NAME, TABLE, type_="check")

    # 3) 重建新约束（只允许 draft / archived）
    op.create_check_constraint(
        CK_NAME,
        TABLE,
        "status in ('draft','archived')",
    )


def downgrade() -> None:
    """Downgrade schema."""

    # ⚠️说明：
    # upgrade 已将 active 合并为 draft，这个过程不可逆。
    # downgrade 只恢复约束范围，不恢复数据。

    op.drop_constraint(CK_NAME, TABLE, type_="check")

    op.create_check_constraint(
        CK_NAME,
        TABLE,
        "status in ('draft','active','archived')",
    )
