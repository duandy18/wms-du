"""create stock_ledger if missing (idempotent)

This migration creates the stock_ledger table on PostgreSQL when it does not exist,
with the target shape required by the Step-2 plan.

Columns:
  id (PK), stock_id (FK -> stocks.id), reason (str32), after_qty (numeric(18,6)),
  delta (numeric(18,6)), occurred_at (timestamptz), ref (str64), ref_line (str32)

Also adds:
  - FK(stock_id) -> stocks(id)
  - UNIQUE(reason, ref, ref_line)
  - helpful indexes on (stock_id) and (occurred_at)
"""

from __future__ import annotations
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# keep short revision id to avoid VARCHAR(32) limits on vanilla setups
revision = "40a7b8b5e6d1"
down_revision = "3a_fix_sqlite_inline_pks"  # 让它接在你当前主链头之后
branch_labels = None
depends_on = None

TABLE = "stock_ledger"

def upgrade() -> None:
    bind = op.get_bind()
    # 1) 若表已存在，直接返回（幂等）
    exists = bind.execute(text("SELECT to_regclass(:t) IS NOT NULL"), {"t": TABLE}).scalar()
    if exists:
        return

    # 2) 创建表（目标形状）
    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("stock_id", sa.Integer, nullable=False),
        sa.Column("reason", sa.String(length=32), nullable=False),
        sa.Column("after_qty", sa.Numeric(18, 6), nullable=False),
        sa.Column("delta", sa.Numeric(18, 6), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ref", sa.String(length=64), nullable=True),
        sa.Column("ref_line", sa.String(length=32), nullable=True),
    )

    # 3) 约束与索引
    op.create_foreign_key(
        "fk_stock_ledger_stock_id_stocks",
        source_table=TABLE,
        referent_table="stocks",
        local_cols=["stock_id"],
        remote_cols=["id"],
        ondelete="RESTRICT",
        onupdate="CASCADE",
    )
    op.create_unique_constraint(
        "uq_stock_ledger_reason_ref_refline",
        TABLE,
        ["reason", "ref", "ref_line"],
    )
    op.create_index("ix_stock_ledger_stock_id", TABLE, ["stock_id"])
    op.create_index("ix_stock_ledger_occurred_at", TABLE, ["occurred_at"])

def downgrade() -> None:
    # 仅在本迁移创建的表存在时回滚
    bind = op.get_bind()
    exists = bind.execute(text("SELECT to_regclass(:t) IS NOT NULL"), {"t": TABLE}).scalar()
    if exists:
        op.drop_table(TABLE)
