"""add shipping_providers table

Revision ID: c6f9efa91e1b
Revises: f773b825e32c
Create Date: 2025-11-27 18:38:57.711135
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c6f9efa91e1b"
down_revision: Union[str, Sequence[str], None] = "f773b825e32c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ------------------------------- 工具函数 -------------------------------

def _has_table(name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    try:
        return insp.has_table(name)  # type: ignore[attr-defined]
    except Exception:
        return name in insp.get_table_names()


def _index_names(table: str) -> set[str]:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    try:
        return {ix["name"] for ix in insp.get_indexes(table)}
    except Exception:
        return set()


def _unique_names(table: str) -> set[str]:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    try:
        return {uc["name"] for uc in insp.get_unique_constraints(table)}
    except Exception:
        return set()


# -------------------------------- upgrade --------------------------------

def upgrade() -> None:
    if not _has_table("shipping_providers"):
        op.create_table(
            "shipping_providers",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("code", sa.String(length=64), nullable=True),

            sa.Column("contact_name", sa.String(length=100), nullable=True),
            sa.Column("phone", sa.String(length=50), nullable=True),
            sa.Column("email", sa.String(length=255), nullable=True),
            sa.Column("wechat", sa.String(length=64), nullable=True),

            sa.Column(
                "active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("TRUE"),
            ),

            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )

    # 唯一约束
    uqs = _unique_names("shipping_providers")
    if "uq_shipping_providers_name" not in uqs:
        op.create_unique_constraint(
            "uq_shipping_providers_name",
            "shipping_providers",
            ["name"],
        )
    if "uq_shipping_providers_code" not in uqs:
        op.create_unique_constraint(
            "uq_shipping_providers_code",
            "shipping_providers",
            ["code"],
        )

    # 索引
    idx = _index_names("shipping_providers")
    if "ix_shipping_providers_active" not in idx:
        op.create_index(
            "ix_shipping_providers_active",
            "shipping_providers",
            ["active"],
            unique=False,
        )
    if "ix_shipping_providers_name" not in idx:
        op.create_index(
            "ix_shipping_providers_name",
            "shipping_providers",
            ["name"],
            unique=False,
        )


# -------------------------------- downgrade --------------------------------

def downgrade() -> None:
    if _has_table("shipping_providers"):
        idx = _index_names("shipping_providers")
        if "ix_shipping_providers_name" in idx:
            op.drop_index(
                "ix_shipping_providers_name",
                table_name="shipping_providers",
            )
        if "ix_shipping_providers_active" in idx:
            op.drop_index(
                "ix_shipping_providers_active",
                table_name="shipping_providers",
            )

        uqs = _unique_names("shipping_providers")
        if "uq_shipping_providers_name" in uqs:
            op.drop_constraint(
                "uq_shipping_providers_name",
                "shipping_providers",
                type_="unique",
            )
        if "uq_shipping_providers_code" in uqs:
            op.drop_constraint(
                "uq_shipping_providers_code",
                "shipping_providers",
                type_="unique",
            )

        op.drop_table("shipping_providers")
