"""add pricing_scheme_dest_adjustments

Revision ID: 54e1cf6ab525
Revises: 52d1f9ef04c2
Create Date: 2026-01-31 11:37:00.861985
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "54e1cf6ab525"
down_revision: Union[str, Sequence[str], None] = "52d1f9ef04c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pricing_scheme_dest_adjustments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("scheme_id", sa.Integer(), nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("province", sa.String(length=64), nullable=False),
        sa.Column("city", sa.String(length=64), nullable=True),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column(
            "active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "priority",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("100"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["scheme_id"],
            ["shipping_provider_pricing_schemes.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "scheme_id",
            "scope",
            "province",
            "city",
            name="uq_scheme_dest_adj_scope_province_city",
        ),
        sa.CheckConstraint(
            "scope in ('province','city')",
            name="ck_scheme_dest_adj_scope",
        ),
    )


def downgrade() -> None:
    op.drop_table("pricing_scheme_dest_adjustments")
