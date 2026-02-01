"""datafix: collapse fake batch codes to NULL slot for non-batch items

只处理：
- items.has_shelf_life IS NOT TRUE（非批次受控）
- batch_code 属于历史假码/污染码（大小写不敏感）：
  * NOEXP / NEAR / FAR / IDEM
  * None（曾出现过 None 被 str() 写入为字符串的污染）

做三件事：
1) stocks：把这些假 batch_code 的 qty 合并到 batch_code=NULL 槽位，并删除假槽位
2) stock_ledger：把这些假 batch_code 的 batch_code 置为 NULL
3) 备份：提供 downgrade 所需的最小可逆信息

注意：
- 不触碰 requires_batch=true 的商品
- 不触碰 batches 主档（仅库存/台账事实修复）
- 若出现幂等唯一冲突，将 fail-fast（避免静默数据损坏）
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "16203ca6ea03"
down_revision: Union[str, Sequence[str], None] = "63d3e537d7f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ✅ 假码集合（统一用 lower() 比较，大小写不敏感）
# - 'none'：防止 None 被 str() 污染写入
_FAKE_CODES_LOWER = ("noexp", "near", "far", "idem", "none")
_SENTINEL = "__NULL_BATCH__"


def upgrade() -> None:
    bind = op.get_bind()
    codes = list(_FAKE_CODES_LOWER)

    # ============================================================
    # 0) Backup tables（仅用于本次 datafix，可回滚）
    # ============================================================
    bind.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS datafix_no_batch_stocks_backup (
                warehouse_id   INTEGER NOT NULL,
                item_id        INTEGER NOT NULL,
                batch_code     VARCHAR(64),
                qty            INTEGER NOT NULL,
                backed_at      TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            """
        )
    )

    bind.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS datafix_no_batch_stocks_null_backup (
                warehouse_id     INTEGER NOT NULL,
                item_id          INTEGER NOT NULL,
                qty_null_before  INTEGER NOT NULL,
                backed_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
                PRIMARY KEY (warehouse_id, item_id)
            );
            """
        )
    )

    bind.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS datafix_no_batch_ledger_backup (
                ledger_id   INTEGER PRIMARY KEY,
                batch_code  VARCHAR(64),
                backed_at   TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            """
        )
    )

    # ============================================================
    # 1) stocks：备份假批次槽位 & 备份 NULL 槽位原始 qty
    # ============================================================
    bind.execute(
        sa.text(
            """
            INSERT INTO datafix_no_batch_stocks_backup (warehouse_id, item_id, batch_code, qty)
            SELECT s.warehouse_id, s.item_id, s.batch_code, s.qty
              FROM stocks s
              JOIN items i ON i.id = s.item_id
             WHERE i.has_shelf_life IS NOT TRUE
               AND s.batch_code IS NOT NULL
               AND lower(s.batch_code) = ANY(:codes)
            """
        ),
        {"codes": codes},
    )

    bind.execute(
        sa.text(
            """
            INSERT INTO datafix_no_batch_stocks_null_backup (warehouse_id, item_id, qty_null_before)
            SELECT x.warehouse_id,
                   x.item_id,
                   COALESCE(n.qty, 0) AS qty_null_before
              FROM (
                    SELECT DISTINCT s.warehouse_id, s.item_id
                      FROM stocks s
                      JOIN items i ON i.id = s.item_id
                     WHERE i.has_shelf_life IS NOT TRUE
                       AND s.batch_code IS NOT NULL
                       AND lower(s.batch_code) = ANY(:codes)
                   ) x
              LEFT JOIN stocks n
                     ON n.warehouse_id = x.warehouse_id
                    AND n.item_id      = x.item_id
                    AND n.batch_code IS NULL
            ON CONFLICT (warehouse_id, item_id) DO NOTHING
            """
        ),
        {"codes": codes},
    )

    # ============================================================
    # 2) stocks：合并 qty → NULL 槽位，然后删除假槽位
    # ============================================================
    bind.execute(
        sa.text(
            """
            WITH agg AS (
                SELECT s.warehouse_id,
                       s.item_id,
                       SUM(s.qty) AS add_qty
                  FROM stocks s
                  JOIN items i ON i.id = s.item_id
                 WHERE i.has_shelf_life IS NOT TRUE
                   AND s.batch_code IS NOT NULL
                   AND lower(s.batch_code) = ANY(:codes)
                 GROUP BY s.warehouse_id, s.item_id
            )
            INSERT INTO stocks (warehouse_id, item_id, batch_code, qty)
            SELECT a.warehouse_id,
                   a.item_id,
                   NULL::varchar(64) AS batch_code,
                   a.add_qty
              FROM agg a
            ON CONFLICT ON CONSTRAINT uq_stocks_item_wh_batch
            DO UPDATE SET qty = stocks.qty + EXCLUDED.qty
            """
        ),
        {"codes": codes},
    )

    bind.execute(
        sa.text(
            """
            DELETE FROM stocks s
             USING items i
             WHERE i.id = s.item_id
               AND i.has_shelf_life IS NOT TRUE
               AND s.batch_code IS NOT NULL
               AND lower(s.batch_code) = ANY(:codes)
            """
        ),
        {"codes": codes},
    )

    # ============================================================
    # 3) stock_ledger：备份后置 NULL
    # ============================================================
    bind.execute(
        sa.text(
            """
            INSERT INTO datafix_no_batch_ledger_backup (ledger_id, batch_code)
            SELECT l.id, l.batch_code
              FROM stock_ledger l
              JOIN items i ON i.id = l.item_id
             WHERE i.has_shelf_life IS NOT TRUE
               AND l.batch_code IS NOT NULL
               AND lower(l.batch_code) = ANY(:codes)
            ON CONFLICT (ledger_id) DO NOTHING
            """
        ),
        {"codes": codes},
    )

    # fail-fast：若更新为 NULL 后撞到唯一约束，会直接抛错并回滚整个迁移
    bind.execute(
        sa.text(
            """
            UPDATE stock_ledger l
               SET batch_code = NULL
              FROM items i
             WHERE i.id = l.item_id
               AND i.has_shelf_life IS NOT TRUE
               AND l.batch_code IS NOT NULL
               AND lower(l.batch_code) = ANY(:codes)
            """
        ),
        {"codes": codes},
    )


def downgrade() -> None:
    bind = op.get_bind()

    # 1) 恢复 stock_ledger.batch_code
    bind.execute(
        sa.text(
            """
            UPDATE stock_ledger l
               SET batch_code = b.batch_code
              FROM datafix_no_batch_ledger_backup b
             WHERE b.ledger_id = l.id
            """
        )
    )

    # 2) 恢复 NULL 槽位 qty
    bind.execute(
        sa.text(
            """
            UPDATE stocks s
               SET qty = nb.qty_null_before
              FROM datafix_no_batch_stocks_null_backup nb
             WHERE s.warehouse_id = nb.warehouse_id
               AND s.item_id = nb.item_id
               AND s.batch_code IS NULL
            """
        )
    )

    # 3) 恢复假批次 stocks 行（用 upsert 覆盖 qty）
    bind.execute(
        sa.text(
            """
            INSERT INTO stocks (warehouse_id, item_id, batch_code, qty)
            SELECT b.warehouse_id, b.item_id, b.batch_code, b.qty
              FROM datafix_no_batch_stocks_backup b
            ON CONFLICT ON CONSTRAINT uq_stocks_item_wh_batch
            DO UPDATE SET qty = EXCLUDED.qty
            """
        )
    )
