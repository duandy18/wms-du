"""batches unique + indexes (with dedup)

Revision ID: 8cc9988c7301
Revises: 20251024_drop_legacy_ledger_uc_by_columns
Create Date: 2025-10-25 11:37:01.452669
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8cc9988c7301"
down_revision: Union[str, Sequence[str], None] = "20251024_drop_legacy_ledger_uc_by_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---------- 0) 先合并重复：同 (item_id, warehouse_id, location_id, batch_code) 仅保留最新一条，qty 合计 ----------
    # 把最新一条（id 最大，rn=1）的 qty 更新为同组合的合计
    op.execute(sa.text("""
        WITH ranked AS (
          SELECT
            id, item_id, warehouse_id, location_id, batch_code, qty,
            ROW_NUMBER() OVER (
              PARTITION BY item_id, warehouse_id, location_id, batch_code
              ORDER BY id DESC
            ) AS rn,
            SUM(COALESCE(qty,0)) OVER (
              PARTITION BY item_id, warehouse_id, location_id, batch_code
            ) AS sum_qty
          FROM batches
        )
        UPDATE batches b
        SET qty = r.sum_qty
        FROM ranked r
        WHERE b.id = r.id
          AND r.rn = 1
          AND r.sum_qty IS NOT NULL
    """))

    # 删除其余重复行（rn > 1）
    op.execute(sa.text("""
        WITH ranked AS (
          SELECT
            id, item_id, warehouse_id, location_id, batch_code,
            ROW_NUMBER() OVER (
              PARTITION BY item_id, warehouse_id, location_id, batch_code
              ORDER BY id DESC
            ) AS rn
          FROM batches
        )
        DELETE FROM batches b
        USING ranked r
        WHERE b.id = r.id
          AND r.rn > 1
    """))

    # ---------- 1) 创建唯一约束 ----------
    op.create_unique_constraint(
        "uq_batches_item_wh_loc_code",
        "batches",
        ["item_id", "warehouse_id", "location_id", "batch_code"],
    )

    # ---------- 2) 常用索引（FEFO / 近效期） ----------
    op.create_index(
        "ix_batches_item_loc_expiry",
        "batches",
        ["item_id", "location_id", "expiry_date", "id"],
        unique=False,
    )
    op.create_index(
        "ix_batches_wh_expiry",
        "batches",
        ["warehouse_id", "expiry_date", "id"],
        unique=False,
    )


def downgrade() -> None:
    # 回滚：先删约束与索引（数据不回拆）
    with op.batch_alter_table("batches") as batch_op:
        batch_op.drop_constraint("uq_batches_item_wh_loc_code", type_="unique")
    op.drop_index("ix_batches_wh_expiry", table_name="batches")
    op.drop_index("ix_batches_item_loc_expiry", table_name="batches")
