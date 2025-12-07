"""Drop legacy columns from stocks after views have been rewritten

This migration verifies that NO view still depends on:
  - stocks.batch_code
  - stocks.warehouse_id
Then drops:
  - FK (warehouse_id -> warehouses) if exists
  - columns batch_code, warehouse_id

Revision ID: 20251104_drop_stocks_legacy_columns
Revises: 20251104_rewrite_v_putaway_ledger_recent
Create Date: 2025-11-04 22:48:00
"""

from __future__ import annotations

from typing import Optional, Sequence

from alembic import op
import sqlalchemy as sa

# ---- Alembic identifiers ----
revision: str = "20251104_drop_stocks_legacy_columns"
down_revision: Optional[str] = "20251104_rewrite_v_putaway_ledger_recent"
branch_labels: Optional[Sequence[str]] = None
depends_on: Optional[Sequence[str]] = None
# -----------------------------


def upgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)

    def has_column(name: str) -> bool:
        return any(c["name"] == name for c in insp.get_columns("stocks"))

    # 0) 依赖检查：如果仍有视图引用这些列，则拒绝删除并给出说明
    for col in ("batch_code", "warehouse_id"):
        count = conn.execute(
            sa.text("""
            SELECT COUNT(*) FROM information_schema.view_column_usage
             WHERE table_schema='public' AND table_name='stocks' AND column_name=:col
        """),
            {"col": col},
        ).scalar_one()
        if count and count > 0:
            raise RuntimeError(
                f"Cannot drop stocks.{col}: {count} dependent view column usage remains. "
                f"Please ensure all views use v_stocks_enriched / batches / locations instead."
            )

    # 1) 删除 warehouse_id 的 FK（若存在）
    for fk in insp.get_foreign_keys("stocks"):
        if (
            fk.get("constrained_columns") == ["warehouse_id"]
            and fk.get("referred_table") == "warehouses"
        ):
            op.drop_constraint(fk["name"], "stocks", type_="foreignkey")
            break

    # 2) 删除列（存在才删）
    if has_column("batch_code"):
        op.drop_column("stocks", "batch_code")
    if has_column("warehouse_id"):
        op.drop_column("stocks", "warehouse_id")


def downgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)

    def has_column(name: str) -> bool:
        return any(c["name"] == name for c in insp.get_columns("stocks"))

    # 回滚：加回列（可空）
    if not has_column("warehouse_id"):
        op.add_column("stocks", sa.Column("warehouse_id", sa.Integer(), nullable=True))
    if not has_column("batch_code"):
        op.add_column("stocks", sa.Column("batch_code", sa.String(length=64), nullable=True))

    # 恢复 FK（若不存在）
    if not any(
        fk.get("constrained_columns") == ["warehouse_id"]
        and fk.get("referred_table") == "warehouses"
        for fk in insp.get_foreign_keys("stocks")
    ):
        op.create_foreign_key(
            "fk_stocks_warehouse",
            "stocks",
            "warehouses",
            local_cols=["warehouse_id"],
            remote_cols=["id"],
            deferrable=True,
            initially="DEFERRED",
        )
