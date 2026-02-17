"""add inbound_receipt_drafts

Revision ID: 0f94288a837b
Revises: b22f0c8703d4
Create Date: 2026-02-17 19:49:40.301577

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0f94288a837b"
down_revision: Union[str, Sequence[str], None] = "b22f0c8703d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    目标：引入“草稿收货单”执行层（不污染 inbound_receipts / inbound_receipt_lines 事实凭证层）
    - inbound_receipt_drafts：草稿头（对照 PO，状态 DRAFT/COMMITTED）
    - inbound_receipt_draft_lines：草稿行（对照 po_line_id 打勾 + 可逐步补齐 qty/batch/dates）
    """
    # ---------- 1) drafts ----------
    op.create_table(
        "inbound_receipt_drafts",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("po_id", sa.Integer(), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=True),
        sa.Column("supplier_name", sa.String(length=255), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="DRAFT",
        ),
        sa.Column("ref", sa.String(length=128), nullable=False),
        sa.Column("remark", sa.String(length=255), nullable=True),
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
    )

    # FK：对照采购单/供应商/仓库
    op.create_foreign_key(
        "fk_inbound_receipt_drafts_po",
        "inbound_receipt_drafts",
        "purchase_orders",
        ["po_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_inbound_receipt_drafts_warehouse",
        "inbound_receipt_drafts",
        "warehouses",
        ["warehouse_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_inbound_receipt_drafts_supplier",
        "inbound_receipt_drafts",
        "suppliers",
        ["supplier_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 索引：常用查询
    op.create_index(
        "ix_inbound_receipt_drafts_po_id",
        "inbound_receipt_drafts",
        ["po_id"],
    )
    op.create_index(
        "ix_inbound_receipt_drafts_wh",
        "inbound_receipt_drafts",
        ["warehouse_id"],
    )
    op.create_index(
        "ix_inbound_receipt_drafts_ref",
        "inbound_receipt_drafts",
        ["ref"],
    )
    op.create_index(
        "ix_inbound_receipt_drafts_created_at",
        "inbound_receipt_drafts",
        ["created_at"],
    )

    # ✅ 合同：同一 PO 仅允许一个活跃 DRAFT（Postgres partial unique index）
    op.create_index(
        "uq_inbound_receipt_drafts_po_active",
        "inbound_receipt_drafts",
        ["po_id"],
        unique=True,
        postgresql_where=sa.text("status = 'DRAFT'"),
    )

    # ---------- 2) draft lines ----------
    op.create_table(
        "inbound_receipt_draft_lines",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("draft_id", sa.BigInteger(), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("po_line_id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        # 草稿允许逐步补齐：qty/batch/dates 均可为空（commit 前强校验）
        sa.Column("qty", sa.Integer(), nullable=True),
        sa.Column("batch_code", sa.String(length=64), nullable=True),
        sa.Column("production_date", sa.Date(), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("remark", sa.String(length=255), nullable=True),
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
    )

    op.create_foreign_key(
        "fk_inbound_receipt_draft_lines_draft",
        "inbound_receipt_draft_lines",
        "inbound_receipt_drafts",
        ["draft_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_inbound_receipt_draft_lines_po_line",
        "inbound_receipt_draft_lines",
        "purchase_order_lines",
        ["po_line_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_inbound_receipt_draft_lines_item",
        "inbound_receipt_draft_lines",
        "items",
        ["item_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.create_index(
        "ix_inbound_receipt_draft_lines_draft",
        "inbound_receipt_draft_lines",
        ["draft_id"],
    )
    op.create_index(
        "ix_inbound_receipt_draft_lines_po_line_id",
        "inbound_receipt_draft_lines",
        ["po_line_id"],
    )
    op.create_index(
        "ix_inbound_receipt_draft_lines_item_id",
        "inbound_receipt_draft_lines",
        ["item_id"],
    )

    # ✅ 合同：一个草稿内，同一 po_line 只能勾选一次
    op.create_index(
        "uq_inbound_receipt_draft_lines_draft_po_line",
        "inbound_receipt_draft_lines",
        ["draft_id", "po_line_id"],
        unique=True,
    )

    # ✅ 合同：行号在草稿内唯一（便于稳定排序/展示）
    op.create_index(
        "uq_inbound_receipt_draft_lines_draft_line_no",
        "inbound_receipt_draft_lines",
        ["draft_id", "line_no"],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    # 先删 lines（依赖 drafts）
    op.drop_index("uq_inbound_receipt_draft_lines_draft_line_no", table_name="inbound_receipt_draft_lines")
    op.drop_index("uq_inbound_receipt_draft_lines_draft_po_line", table_name="inbound_receipt_draft_lines")
    op.drop_index("ix_inbound_receipt_draft_lines_item_id", table_name="inbound_receipt_draft_lines")
    op.drop_index("ix_inbound_receipt_draft_lines_po_line_id", table_name="inbound_receipt_draft_lines")
    op.drop_index("ix_inbound_receipt_draft_lines_draft", table_name="inbound_receipt_draft_lines")

    op.drop_constraint("fk_inbound_receipt_draft_lines_item", "inbound_receipt_draft_lines", type_="foreignkey")
    op.drop_constraint("fk_inbound_receipt_draft_lines_po_line", "inbound_receipt_draft_lines", type_="foreignkey")
    op.drop_constraint("fk_inbound_receipt_draft_lines_draft", "inbound_receipt_draft_lines", type_="foreignkey")

    op.drop_table("inbound_receipt_draft_lines")

    # 再删 drafts
    op.drop_index("uq_inbound_receipt_drafts_po_active", table_name="inbound_receipt_drafts")
    op.drop_index("ix_inbound_receipt_drafts_created_at", table_name="inbound_receipt_drafts")
    op.drop_index("ix_inbound_receipt_drafts_ref", table_name="inbound_receipt_drafts")
    op.drop_index("ix_inbound_receipt_drafts_wh", table_name="inbound_receipt_drafts")
    op.drop_index("ix_inbound_receipt_drafts_po_id", table_name="inbound_receipt_drafts")

    op.drop_constraint("fk_inbound_receipt_drafts_supplier", "inbound_receipt_drafts", type_="foreignkey")
    op.drop_constraint("fk_inbound_receipt_drafts_warehouse", "inbound_receipt_drafts", type_="foreignkey")
    op.drop_constraint("fk_inbound_receipt_drafts_po", "inbound_receipt_drafts", type_="foreignkey")

    op.drop_table("inbound_receipt_drafts")
