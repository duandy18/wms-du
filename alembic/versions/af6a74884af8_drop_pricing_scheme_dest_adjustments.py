"""drop_pricing_scheme_dest_adjustments

Revision ID: af6a74884af8
Revises: f9ef082d9fcf
Create Date: 2026-03-06

目标：
- 删除已退役表 pricing_scheme_dest_adjustments
- 该表数据已迁移到 shipping_provider_surcharges
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "af6a74884af8"
down_revision: Union[str, Sequence[str], None] = "f9ef082d9fcf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "pricing_scheme_dest_adjustments"


def upgrade() -> None:
    """Drop legacy destination adjustment table."""
    op.drop_table(TABLE)


def downgrade() -> None:
    """Recreate table for rollback (structure snapshot)."""
    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("scheme_id", sa.Integer(), nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("province", sa.String(length=64), nullable=False),
        sa.Column("city", sa.String(length=64), nullable=True),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("100")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("province_code", sa.String(length=32), nullable=False),
        sa.Column("city_code", sa.String(length=32), nullable=True),
        sa.Column("province_name", sa.String(length=64), nullable=True),
        sa.Column("city_name", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(
            ["scheme_id"],
            ["shipping_provider_pricing_schemes.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "scheme_id",
            "scope",
            "province_code",
            "city_code",
            name="uq_scheme_dest_adj_scope_provcode_citycode",
        ),
        sa.CheckConstraint(
            "scope in ('province','city')",
            name="ck_scheme_dest_adj_scope",
        ),
    )
