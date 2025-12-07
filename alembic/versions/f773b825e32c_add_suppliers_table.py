"""add suppliers table

Revision ID: f773b825e32c
Revises: ac53a14e9f34
Create Date: 2025-11-27 18:07:13.604597
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f773b825e32c"
down_revision: Union[str, Sequence[str], None] = "ac53a14e9f34"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ------------------------------- 工具函数（统一风格） -------------------------------

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


# -------------------------------------- upgrade --------------------------------------

def upgrade() -> None:
    if not _has_table("suppliers"):
        op.create_table(
            "suppliers",
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

    # 唯一约束检查（但不重复创建）
    uqs = _unique_names("suppliers")
    if "uq_suppliers_name" not in uqs:
        op.create_unique_constraint("uq_suppliers_name", "suppliers", ["name"])
    if "uq_suppliers_code" not in uqs:
        op.create_unique_constraint("uq_suppliers_code", "suppliers", ["code"])

    # 索引
    idx = _index_names("suppliers")
    if "ix_suppliers_active" not in idx:
        op.create_index(
            "ix_suppliers_active",
            "suppliers",
            ["active"],
            unique=False,
        )
    if "ix_suppliers_name" not in idx:
        op.create_index(
            "ix_suppliers_name",
            "suppliers",
            ["name"],
            unique=False,
        )


# -------------------------------------- downgrade --------------------------------------

def downgrade() -> None:
    if _has_table("suppliers"):
        idx = _index_names("suppliers")
        if "ix_suppliers_name" in idx:
            op.drop_index("ix_suppliers_name", table_name="suppliers")
        if "ix_suppliers_active" in idx:
            op.drop_index("ix_suppliers_active", table_name="suppliers")

        uqs = _unique_names("suppliers")
        if "uq_suppliers_name" in uqs:
            op.drop_constraint("uq_suppliers_name", "suppliers", type_="unique")
        if "uq_suppliers_code" in uqs:
            op.drop_constraint("uq_suppliers_code", "suppliers", type_="unique")

        op.drop_table("suppliers")
