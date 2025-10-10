"""fix item qty_available (SQLite safe)

Revision ID: 1a189010e7b4
Revises: dad463872aef
Create Date: 2025-10-06 10:03:37.475811
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "1a189010e7b4"
down_revision: str | Sequence[str] | None = "dad463872aef"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def column_exists(table_name: str, column_name: str) -> bool:
    """检查列是否已存在（SQLite 专用）"""
    conn = op.get_bind()
    result = conn.execute(sa.text(f"PRAGMA table_info({table_name});"))
    return any(row[1] == column_name for row in result.fetchall())


def upgrade() -> None:
    """只在缺列时添加 qty_available"""
    if not column_exists("items", "qty_available"):
        op.add_column(
            "items",
            sa.Column("qty_available", sa.Integer(), nullable=False, server_default="0"),
        )
    else:
        print("⚠️  已存在列 items.qty_available，跳过添加。")


def downgrade() -> None:
    """可选回滚（SQLite 旧版本可能不支持 drop_column）"""
    try:
        op.drop_column("items", "qty_available")
    except Exception as e:
        print("⚠️  SQLite 忽略 drop_column:", e)
