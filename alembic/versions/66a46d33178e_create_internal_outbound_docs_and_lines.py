"""create internal outbound docs and lines

Revision ID: 66a46d33178e
Revises: 11fce062778b
Create Date: 2025-12-09 18:35:34.642753
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "66a46d33178e"
down_revision: Union[str, Sequence[str], None] = "11fce062778b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- 内部出库单头表 ---
    op.create_table(
        "internal_outbound_docs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("warehouse_id", sa.BigInteger(), nullable=False),
        sa.Column("doc_no", sa.Text(), nullable=False),
        sa.Column("doc_type", sa.Text(), nullable=False),  # SAMPLE_OUT / INTERNAL_USE / SCRAP ...
        sa.Column("status", sa.Text(), nullable=False, server_default="DRAFT"),

        # 领取人信息
        sa.Column("recipient_name", sa.Text(), nullable=True),
        sa.Column("recipient_id", sa.BigInteger(), nullable=True),
        sa.Column("recipient_type", sa.Text(), nullable=True),
        sa.Column("recipient_note", sa.Text(), nullable=True),

        # 备注 / 审计
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("confirmed_by", sa.BigInteger(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("canceled_by", sa.BigInteger(), nullable=True),
        sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True),

        # trace / 扩展
        sa.Column("trace_id", sa.Text(), nullable=True),
        sa.Column("extra_meta", sa.JSON(), nullable=True),
    )

    # 外键（仓库 + 用户）
    op.create_foreign_key(
        "fk_internal_outbound_docs_warehouse_id",
        "internal_outbound_docs",
        "warehouses",
        ["warehouse_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_internal_outbound_docs_created_by",
        "internal_outbound_docs",
        "users",
        ["created_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_internal_outbound_docs_confirmed_by",
        "internal_outbound_docs",
        "users",
        ["confirmed_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_internal_outbound_docs_canceled_by",
        "internal_outbound_docs",
        "users",
        ["canceled_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_internal_outbound_docs_recipient_id",
        "internal_outbound_docs",
        "users",
        ["recipient_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 索引
    op.create_index(
        "ix_internal_outbound_docs_warehouse_doc_no",
        "internal_outbound_docs",
        ["warehouse_id", "doc_no"],
        unique=True,
    )
    op.create_index(
        "ix_internal_outbound_docs_trace_id",
        "internal_outbound_docs",
        ["trace_id"],
    )
    op.create_index(
        "ix_internal_outbound_docs_status",
        "internal_outbound_docs",
        ["status"],
    )

    # --- 内部出库单行表 ---
    op.create_table(
        "internal_outbound_lines",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("doc_id", sa.BigInteger(), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.BigInteger(), nullable=False),
        sa.Column("batch_code", sa.Text(), nullable=True),
        sa.Column("requested_qty", sa.Integer(), nullable=False),
        sa.Column("confirmed_qty", sa.Integer(), nullable=True),
        sa.Column("uom", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("extra_meta", sa.JSON(), nullable=True),
    )

    # FK
    op.create_foreign_key(
        "fk_internal_outbound_lines_doc_id",
        "internal_outbound_lines",
        "internal_outbound_docs",
        ["doc_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_internal_outbound_lines_item_id",
        "internal_outbound_lines",
        "items",
        ["item_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # 索引
    op.create_index(
        "ix_internal_outbound_lines_doc_id",
        "internal_outbound_lines",
        ["doc_id"],
    )
    op.create_index(
        "ix_internal_outbound_lines_item_id",
        "internal_outbound_lines",
        ["item_id"],
    )
    op.create_index(
        "uq_internal_outbound_lines_doc_line_no",
        "internal_outbound_lines",
        ["doc_id", "line_no"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_internal_outbound_lines_doc_line_no", table_name="internal_outbound_lines")
    op.drop_index("ix_internal_outbound_lines_item_id", table_name="internal_outbound_lines")
    op.drop_index("ix_internal_outbound_lines_doc_id", table_name="internal_outbound_lines")
    op.drop_constraint("fk_internal_outbound_lines_item_id", "internal_outbound_lines", type_="foreignkey")
    op.drop_constraint("fk_internal_outbound_lines_doc_id", "internal_outbound_lines", type_="foreignkey")
    op.drop_table("internal_outbound_lines")

    op.drop_index("ix_internal_outbound_docs_status", table_name="internal_outbound_docs")
    op.drop_index("ix_internal_outbound_docs_trace_id", table_name="internal_outbound_docs")
    op.drop_index("ix_internal_outbound_docs_warehouse_doc_no", table_name="internal_outbound_docs")

    op.drop_constraint("fk_internal_outbound_docs_recipient_id", "internal_outbound_docs", type_="foreignkey")
    op.drop_constraint("fk_internal_outbound_docs_canceled_by", "internal_outbound_docs", type_="foreignkey")
    op.drop_constraint("fk_internal_outbound_docs_confirmed_by", "internal_outbound_docs", type_="foreignkey")
    op.drop_constraint("fk_internal_outbound_docs_created_by", "internal_outbound_docs", type_="foreignkey")
    op.drop_constraint("fk_internal_outbound_docs_warehouse_id", "internal_outbound_docs", type_="foreignkey")

    op.drop_table("internal_outbound_docs")
