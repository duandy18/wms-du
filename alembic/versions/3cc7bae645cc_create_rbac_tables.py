"""create_rbac_tables (idempotent stub on top of ef524e72a68a)

Revision ID: 3cc7bae645cc
Revises: ef524e72a68a
Create Date: 2025-11-16 14:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "3cc7bae645cc"
down_revision: Union[str, Sequence[str], None] = "ef524e72a68a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """RBAC 表在前一版本 (ef524e72a68a) 已经创建。

    为了兼容已有环境，这个 migration 只在 roles 表缺失时兜底创建；
    在干净库或已经跑过 ef524 的库中，几乎总是 NOOP。
    """
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 如果 roles 表已经存在，认为 RBAC 体系已准备就绪，直接跳过。
    if insp.has_table("roles", schema="public"):
        return

    # 极端情况兜底：只有在 roles 表真的不存在时，才补一版最小 RBAC 结构。
    op.create_table(
        "roles",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("description", sa.Text, nullable=True),
    )

    op.create_table(
        "permissions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(255), nullable=False, unique=True),
        sa.Column("description", sa.Text, nullable=True),
    )

    op.create_table(
        "role_grants",
        sa.Column("role_id", sa.Integer, nullable=False),
        sa.Column("permission_id", sa.Integer, nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["permission_id"], ["permissions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("role_id", "permission_id"),
    )


def downgrade() -> None:
    """Best-effort rollback."""
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 只在这些表存在时才尝试删除，避免在缺表环境里再次炸掉。
    if insp.has_table("role_grants", schema="public"):
        op.drop_table("role_grants")
    if insp.has_table("permissions", schema="public"):
        op.drop_table("permissions")
    if insp.has_table("roles", schema="public"):
        op.drop_table("roles")
