"""create supplier_contacts table

Revision ID: b794e7b1fa73
Revises: abe0b1aa9a30
Create Date: 2025-12-13 12:47:01.592227

目标（Phase 3 延展）：
- 新建 supplier_contacts 子表（多联系人，最规范）
- 一个 supplier 可有多个联系人
- 同一 supplier 只允许一个主联系人（is_primary=true）
- 删除 supplier：RESTRICT（避免级联抹除联系人历史）
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b794e7b1fa73"
down_revision: Union[str, Sequence[str], None] = "abe0b1aa9a30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "supplier_contacts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),

        sa.Column(
            "supplier_id",
            sa.Integer(),
            sa.ForeignKey("suppliers.id", ondelete="RESTRICT"),
            nullable=False,
        ),

        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("wechat", sa.String(length=64), nullable=True),

        sa.Column(
            "role",
            sa.String(length=32),
            nullable=False,
            server_default="other",
            comment="采购/对账/发货/售后/其他",
        ),

        sa.Column(
            "is_primary",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),

        sa.Column(
            "active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
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

    # 常用索引：按 supplier_id 取联系人
    op.create_index(
        "ix_supplier_contacts_supplier_id",
        "supplier_contacts",
        ["supplier_id"],
    )

    # 强约束：同一 supplier 只允许一个主联系人
    # 用“部分唯一索引”最稳：只对 is_primary=true 的行生效
    op.execute(
        sa.text(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_supplier_contacts_primary_per_supplier
            ON supplier_contacts (supplier_id)
            WHERE is_primary = TRUE;
            """
        )
    )


def downgrade() -> None:
    # 反向清理
    op.execute(
        sa.text(
            """
            DROP INDEX IF EXISTS uq_supplier_contacts_primary_per_supplier;
            """
        )
    )
    op.drop_index("ix_supplier_contacts_supplier_id", table_name="supplier_contacts")
    op.drop_table("supplier_contacts")
