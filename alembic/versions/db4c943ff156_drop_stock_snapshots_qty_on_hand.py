"""drop stock_snapshots.qty_on_hand

Revision ID: db4c943ff156
Revises: cc3a2e54e5ce
Create Date: 2026-02-02 03:22:32.909159
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "db4c943ff156"
down_revision: Union[str, Sequence[str], None] = "cc3a2e54e5ce"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Stage C.2-2：最终删除 stock_snapshots.qty_on_hand

    动作：
    1) 移除 trigger / function（不再需要双写同步）
    2) drop 列 qty_on_hand
    """
    op.execute("DROP TRIGGER IF EXISTS trg_stock_snapshots_sync_qty_cols ON stock_snapshots;")
    op.execute("DROP FUNCTION IF EXISTS stock_snapshots_sync_qty_cols();")
    op.drop_column("stock_snapshots", "qty_on_hand")


def downgrade() -> None:
    """
    Best-effort downgrade：
    1) 加回 qty_on_hand 并用 qty 回填
    2) 恢复同步函数与 trigger（使用修复后的版本）
    """
    op.add_column(
        "stock_snapshots",
        sa.Column("qty_on_hand", sa.Numeric(18, 4), nullable=False, server_default=sa.text("0")),
    )
    op.execute("UPDATE stock_snapshots SET qty_on_hand = qty")
    op.alter_column("stock_snapshots", "qty_on_hand", server_default=None)

    op.execute(
        """
        CREATE OR REPLACE FUNCTION stock_snapshots_sync_qty_cols()
        RETURNS trigger AS $$
        BEGIN
          IF TG_OP = 'INSERT' THEN
            IF NEW.qty IS NOT NULL
               AND NEW.qty != 0
               AND (NEW.qty_on_hand IS NULL OR NEW.qty_on_hand = 0) THEN
              NEW.qty_on_hand := NEW.qty;
              RETURN NEW;
            END IF;

            IF NEW.qty_on_hand IS NOT NULL
               AND NEW.qty_on_hand != 0
               AND (NEW.qty IS NULL OR NEW.qty = 0) THEN
              NEW.qty := NEW.qty_on_hand;
              RETURN NEW;
            END IF;

            IF NEW.qty IS NOT NULL
               AND NEW.qty_on_hand IS NOT NULL
               AND NEW.qty IS DISTINCT FROM NEW.qty_on_hand THEN
              NEW.qty_on_hand := NEW.qty;
              RETURN NEW;
            END IF;

            RETURN NEW;
          END IF;

          IF NEW.qty IS DISTINCT FROM OLD.qty THEN
            NEW.qty_on_hand := NEW.qty;
            RETURN NEW;
          END IF;

          IF NEW.qty_on_hand IS DISTINCT FROM OLD.qty_on_hand THEN
            NEW.qty := NEW.qty_on_hand;
            RETURN NEW;
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
