# alembic/versions/2a01baddb002_add_stock_ledger.py
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "2a01baddb002"  # ← 用 alembic 生成后的真实值替换
down_revision = "2a01baddb001"  # ← 改成 `<rev1>_add_batches` 的真实 revision
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "stock_ledger",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "stock_id", sa.Integer(), sa.ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "batch_id",
            sa.Integer(),
            sa.ForeignKey("batches.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("delta", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=False),
        sa.Column("ref", sa.String(length=128), nullable=True),
        # 统一用数据库时间；SQLite 的 CURRENT_TIMESTAMP 为 UTC
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("after_qty", sa.Integer(), nullable=False),
        sa.CheckConstraint("delta <> 0", name="ck_ledger_delta_nonzero"),
    )

    # 常用查询索引
    op.create_index("ix_ledger_stock_time", "stock_ledger", ["stock_id", "created_at"])
    op.create_index("ix_ledger_batch_time", "stock_ledger", ["batch_id", "created_at"])


def downgrade():
    op.drop_index("ix_ledger_batch_time", table_name="stock_ledger")
    op.drop_index("ix_ledger_stock_time", table_name="stock_ledger")
    op.drop_table("stock_ledger")
