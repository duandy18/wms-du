"""add province_mode to shipping_provider_surcharges

Revision ID: 4f4a1115b080
Revises: cb6da4eb97ef
Create Date: 2026-03-10 12:46:24.420285
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4f4a1115b080"
down_revision: Union[str, Sequence[str], None] = "cb6da4eb97ef"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "shipping_provider_surcharges"


def upgrade() -> None:
    """
    新结构：

    每省只有一种模式：

        province → 全省收费
        cities   → 只对指定城市收费

    算价规则：

        if province_mode == 'cities':
            只有城市规则匹配才收费
        else:
            省规则收费
    """

    op.add_column(
        TABLE,
        sa.Column(
            "province_mode",
            sa.String(length=16),
            nullable=False,
            server_default="province",
        ),
    )

    op.create_check_constraint(
        "ck_sp_surcharges_province_mode",
        TABLE,
        "province_mode in ('province','cities')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_sp_surcharges_province_mode",
        TABLE,
        type_="check",
    )

    op.drop_column(
        TABLE,
        "province_mode",
    )
