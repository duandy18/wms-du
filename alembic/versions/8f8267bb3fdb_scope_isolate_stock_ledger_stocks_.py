"""scope: isolate stock ledger/stocks/snapshots prod vs drill

Revision ID: 8f8267bb3fdb
Revises: 5162a641187e
Create Date: 2026-02-13 10:56:09.685337
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8f8267bb3fdb"
down_revision: Union[str, Sequence[str], None] = "5162a641187e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    第一阶段：库存域 Scope 隔离

    目标：
    - stock_ledger / stocks / stock_snapshots 增加 scope
    - 唯一约束纳入 scope
    - 与 ORM 的 index=True 对齐：创建 ix_*_scope 单列索引
    """

    # 1) enum type（幂等）
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'biz_scope') THEN
                CREATE TYPE biz_scope AS ENUM ('PROD','DRILL');
            END IF;
        END$$;
        """
    )

    # 2) stock_ledger：加 scope + 索引 + 约束升级
    op.add_column(
        "stock_ledger",
        sa.Column(
            "scope",
            sa.Enum("PROD", "DRILL", name="biz_scope"),
            nullable=False,
            server_default="PROD",
        ),
    )

    # ✅ ORM 检测到的新增索引（单列）
    op.create_index("ix_stock_ledger_scope", "stock_ledger", ["scope"])

    op.drop_constraint("uq_ledger_wh_batch_item_reason_ref_line", "stock_ledger", type_="unique")
    op.create_unique_constraint(
        "uq_ledger_wh_batch_item_reason_ref_line",
        "stock_ledger",
        ["scope", "reason", "ref", "ref_line", "item_id", "batch_code_key", "warehouse_id"],
    )

    op.alter_column("stock_ledger", "scope", server_default=None)

    # 3) stocks：加 scope + 索引 + 约束升级
    op.add_column(
        "stocks",
        sa.Column(
            "scope",
            sa.Enum("PROD", "DRILL", name="biz_scope"),
            nullable=False,
            server_default="PROD",
        ),
    )

    # ✅ ORM 检测到的新增索引（单列）
    op.create_index("ix_stocks_scope", "stocks", ["scope"])

    op.drop_constraint("uq_stocks_item_wh_batch", "stocks", type_="unique")
    op.create_unique_constraint(
        "uq_stocks_item_wh_batch",
        "stocks",
        ["scope", "item_id", "warehouse_id", "batch_code_key"],
    )

    op.alter_column("stocks", "scope", server_default=None)

    # 4) stock_snapshots：加 scope + 索引 + 约束升级
    op.add_column(
        "stock_snapshots",
        sa.Column(
            "scope",
            sa.Enum("PROD", "DRILL", name="biz_scope"),
            nullable=False,
            server_default="PROD",
        ),
    )

    # ✅ ORM 检测到的新增索引（单列）
    op.create_index("ix_stock_snapshots_scope", "stock_snapshots", ["scope"])

    op.drop_constraint("uq_stock_snapshot_grain_v2", "stock_snapshots", type_="unique")
    op.create_unique_constraint(
        "uq_stock_snapshot_grain_v2",
        "stock_snapshots",
        ["scope", "snapshot_date", "warehouse_id", "item_id", "batch_code_key"],
    )

    op.alter_column("stock_snapshots", "scope", server_default=None)


def downgrade() -> None:
    """
    回滚（仅 schema 层面回退；DRILL 数据会被抹掉/无法安全合并）
    """

    # 1) stock_snapshots：恢复约束 + drop index + drop column
    op.drop_constraint("uq_stock_snapshot_grain_v2", "stock_snapshots", type_="unique")
    op.create_unique_constraint(
        "uq_stock_snapshot_grain_v2",
        "stock_snapshots",
        ["snapshot_date", "warehouse_id", "item_id", "batch_code_key"],
    )

    op.drop_index("ix_stock_snapshots_scope", table_name="stock_snapshots")
    op.drop_column("stock_snapshots", "scope")

    # 2) stocks：恢复约束 + drop index + drop column
    op.drop_constraint("uq_stocks_item_wh_batch", "stocks", type_="unique")
    op.create_unique_constraint(
        "uq_stocks_item_wh_batch",
        "stocks",
        ["item_id", "warehouse_id", "batch_code_key"],
    )

    op.drop_index("ix_stocks_scope", table_name="stocks")
    op.drop_column("stocks", "scope")

    # 3) stock_ledger：恢复约束 + drop index + drop column
    op.drop_constraint("uq_ledger_wh_batch_item_reason_ref_line", "stock_ledger", type_="unique")
    op.create_unique_constraint(
        "uq_ledger_wh_batch_item_reason_ref_line",
        "stock_ledger",
        ["reason", "ref", "ref_line", "item_id", "batch_code_key", "warehouse_id"],
    )

    op.drop_index("ix_stock_ledger_scope", table_name="stock_ledger")
    op.drop_column("stock_ledger", "scope")

    # 4) enum：仅当无人使用才 drop
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_attribute a
                JOIN pg_class c ON a.attrelid = c.oid
                JOIN pg_type t ON a.atttypid = t.oid
                WHERE t.typname = 'biz_scope'
            ) THEN
                DROP TYPE biz_scope;
            END IF;
        END$$;
        """
    )
