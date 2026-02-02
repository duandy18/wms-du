"""add stock_snapshots.qty and sync with qty_on_hand

Revision ID: 030617d82274
Revises: 0db1a061b39f
Create Date: 2026-02-02 02:49:00.868038
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "030617d82274"
down_revision: Union[str, Sequence[str], None] = "0db1a061b39f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Stage C.2-1: snapshot 口径去 qty_on_hand（第一阶段）

    策略：
    1) 新增 stock_snapshots.qty 作为新的事实列
    2) 回填：qty = qty_on_hand
    3) 建立 trigger，保证新旧列双向同步（兼容旧代码）
    """
    # 1) 新增 qty 列（作为 snapshot 的新事实列）
    op.add_column(
        "stock_snapshots",
        sa.Column(
            "qty",
            sa.Numeric(18, 4),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )

    # 2) 回填历史数据
    op.execute("UPDATE stock_snapshots SET qty = qty_on_hand")

    # 3) 去掉默认值（保持 schema 干净）
    op.alter_column("stock_snapshots", "qty", server_default=None)

    # 4) 同步函数：优先以 NEW.qty 为准；否则回写 NEW.qty_on_hand
    op.execute(
        """
        CREATE OR REPLACE FUNCTION stock_snapshots_sync_qty_cols()
        RETURNS trigger AS $$
        BEGIN
          -- 若新代码写 qty，则同步到旧列
          IF NEW.qty IS DISTINCT FROM COALESCE(OLD.qty, NEW.qty) THEN
            NEW.qty_on_hand := NEW.qty;
          ELSE
            -- 否则认为调用方在写旧列
            NEW.qty := NEW.qty_on_hand;
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_stock_snapshots_sync_qty_cols ON stock_snapshots;
        CREATE TRIGGER trg_stock_snapshots_sync_qty_cols
        BEFORE INSERT OR UPDATE ON stock_snapshots
        FOR EACH ROW
        EXECUTE FUNCTION stock_snapshots_sync_qty_cols();
        """
    )


def downgrade() -> None:
    """
    回滚（best-effort）：
    - 移除 trigger / function
    - 用 qty 回填 qty_on_hand
    - 删除 qty 列
    """
    op.execute("DROP TRIGGER IF EXISTS trg_stock_snapshots_sync_qty_cols ON stock_snapshots;")
    op.execute("DROP FUNCTION IF EXISTS stock_snapshots_sync_qty_cols();")

    # 防御性回填
    op.execute("UPDATE stock_snapshots SET qty_on_hand = qty")

    op.drop_column("stock_snapshots", "qty")
