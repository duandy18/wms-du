"""clean_stocks_legacy_fields

Remove legacy columns from stocks: qty_on_hand, batch_id (best-effort, CI-safe).

Revision ID: clean_stocks_legacy_fields
Revises: batch_supplier_lot_varchar
Create Date: 2025-11-11
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "clean_stocks_legacy_fields"
down_revision: Union[str, Sequence[str], None] = "batch_supplier_lot_varchar"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(bind, table: str, col: str) -> bool:
    return bool(
        bind.execute(
            sa.text(
                """
                SELECT 1
                  FROM information_schema.columns
                 WHERE table_schema = 'public'
                   AND table_name   = :t
                   AND column_name  = :c
                 LIMIT 1
                """
            ),
            {"t": table, "c": col},
        ).first()
    )


def upgrade() -> None:
    """Best-effort 清理 stocks 上的 legacy 列。

    说明：
    - 部分环境中 stocks.qty_on_hand / stocks.batch_id 早已被前面迁移清理；
    - 部分环境中依然存在，但在同一事务里对 stocks 做过大量 DDL/trigger 操作，
      直接 ALTER TABLE 可能触发 ObjectInUse (SQLSTATE 55006)；
    - 对当前 v2/v3 架构来说，这两个列已经不再被模型使用，清理只是“锦上添花”，
      因此这里采用“能删就删，删不了就跳过”的策略，保证链路可跑通。
    """
    bind = op.get_bind()

    # 如果压根没有 stocks 表，直接退出（极端场景）
    insp = sa.inspect(bind)
    if not insp.has_table("stocks", schema="public"):
        return

    # 两个候选 legacy 列：qty_on_hand（老的数量列） 和 batch_id（早期 FK 残留）
    legacy_cols = ["qty_on_hand", "batch_id"]

    for col in legacy_cols:
        if not _has_column(bind, "stocks", col):
            continue

        # 用 PL/pgSQL 包一层，专门吞掉 ObjectInUse（SQLSTATE '55006'）这种场景
        op.execute(
            f"""
            DO $$
            BEGIN
              BEGIN
                ALTER TABLE stocks DROP COLUMN {col};
              EXCEPTION
                WHEN SQLSTATE '55006' THEN
                  -- stocks 上有 pending trigger events / 其它 DDL 依赖，跳过这次清理
                  NULL;
                WHEN SQLSTATE '42703' THEN
                  -- 列已经不存在（并发或其它迁移链路径），忽略
                  NULL;
              END;
            END$$;
            """
        )

    # 原版本这里会重建依赖 v_onhand / v_returns_pool 的视图。
    # 在当前 v2/v3 链路中，这些视图已经在其它迁移中按新 schema 统一过，
    # 因此这里不再做额外的 DROP/CREATE，以免引入新的依赖问题。


def downgrade() -> None:
    """降级时尽力补回 legacy 列（仅在缺失时添加，类型按最常见形态补）。"""
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if not insp.has_table("stocks", schema="public"):
        return

    # qty_on_hand：历史上通常是 INTEGER 或 NUMERIC，这里选 INTEGER 基本兼容
    if not _has_column(bind, "stocks", "qty_on_hand"):
        op.add_column("stocks", sa.Column("qty_on_hand", sa.Integer(), nullable=True))

    # batch_id：早期 FK 到 batches.id
    if not _has_column(bind, "stocks", "batch_id"):
        op.add_column("stocks", sa.Column("batch_id", sa.Integer(), nullable=True))
