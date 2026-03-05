"""fix stock_snapshots qty sync trigger

Revision ID: cc3a2e54e5ce
Revises: 030617d82274
Create Date: 2026-02-02 03:17:58.150734
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "cc3a2e54e5ce"
down_revision: Union[str, Sequence[str], None] = "030617d82274"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    修复 stock_snapshots.qty / qty_on_hand 同步触发器：

    - INSERT：
        * 若写 qty（新代码），同步 qty_on_hand
        * 若写 qty_on_hand（旧代码），同步 qty
        * 若两者都写但不一致：以 qty 为准
    - UPDATE：
        * 谁变了，就同步另一列
    """
    op.execute(
        """
        CREATE OR REPLACE FUNCTION stock_snapshots_sync_qty_cols()
        RETURNS trigger AS $$
        BEGIN
          IF TG_OP = 'INSERT' THEN
            -- 新代码：写 qty（通常非 0），旧列默认 0
            IF NEW.qty IS NOT NULL
               AND NEW.qty != 0
               AND (NEW.qty_on_hand IS NULL OR NEW.qty_on_hand = 0) THEN
              NEW.qty_on_hand := NEW.qty;
              RETURN NEW;
            END IF;

            -- 旧代码：写 qty_on_hand（通常非 0），新列默认 0
            IF NEW.qty_on_hand IS NOT NULL
               AND NEW.qty_on_hand != 0
               AND (NEW.qty IS NULL OR NEW.qty = 0) THEN
              NEW.qty := NEW.qty_on_hand;
              RETURN NEW;
            END IF;

            -- 两者都提供但不一致：新世界优先 qty
            IF NEW.qty IS NOT NULL
               AND NEW.qty_on_hand IS NOT NULL
               AND NEW.qty IS DISTINCT FROM NEW.qty_on_hand THEN
              NEW.qty_on_hand := NEW.qty;
              RETURN NEW;
            END IF;

            RETURN NEW;
          END IF;

          -- UPDATE：判断哪一列发生变化
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


def downgrade() -> None:
    """
    best-effort downgrade：恢复为简单的双向同步逻辑
    """
    op.execute(
        """
        CREATE OR REPLACE FUNCTION stock_snapshots_sync_qty_cols()
        RETURNS trigger AS $$
        BEGIN
          IF NEW.qty IS DISTINCT FROM COALESCE(OLD.qty, NEW.qty) THEN
            NEW.qty_on_hand := NEW.qty;
          ELSE
            NEW.qty := NEW.qty_on_hand;
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
