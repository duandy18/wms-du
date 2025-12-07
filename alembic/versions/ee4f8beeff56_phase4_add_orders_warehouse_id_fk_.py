"""phase4: add orders.warehouse_id + fk + backfill

Revision ID: ee4f8beeff56
Revises: 30605f09a34f
Create Date: 2025-11-16 18:25:48.113938

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ee4f8beeff56"
down_revision: Union[str, Sequence[str], None] = "30605f09a34f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1) 添加列（先允许 NULL，便于回填）
    op.add_column(
        "orders",
        sa.Column("warehouse_id", sa.Integer(), nullable=True),
    )

    # 2) 建外键：orders.warehouse_id -> warehouses.id
    #    ON DELETE SET NULL，避免删仓库时把订单一起删掉
    op.create_foreign_key(
        "fk_orders_warehouse",
        source_table="orders",
        referent_table="warehouses",
        local_cols=["warehouse_id"],
        remote_cols=["id"],
        ondelete="SET NULL",
    )

    # 3) 回填历史数据
    #
    # 规则：
    #   - 按 stores 表的 (platform, shop_id) 归类；
    #   - 对每个 store_id，从 store_warehouse 里选一个“最佳仓”：
    #       * is_top = true 优先
    #       * priority 升序
    #       * warehouse_id 升序
    #
    #   - 将该店所有订单的 orders.warehouse_id 设为这个“最佳仓”（仅更新当前为 NULL 的行）。
    #
    # 注意：
    #   - 没有任何 store_warehouse 记录的店铺不会被更新（保持 NULL）；
    #   - 这与当前默认仓解析逻辑相容。
    op.execute(
        """
        WITH wh_choice AS (
            SELECT
                s.platform,
                s.shop_id,
                -- 对每个 store_id 选一个“最佳仓”
                FIRST_VALUE(sw.warehouse_id) OVER (
                    PARTITION BY s.id
                    ORDER BY
                        sw.is_top DESC,
                        sw.priority ASC,
                        sw.warehouse_id ASC
                ) AS warehouse_id
            FROM stores s
            JOIN store_warehouse sw
              ON sw.store_id = s.id
        ),
        wh_choice_dedup AS (
            SELECT DISTINCT platform, shop_id, warehouse_id
            FROM wh_choice
        )
        UPDATE orders o
           SET warehouse_id = c.warehouse_id
          FROM wh_choice_dedup c
         WHERE o.platform = c.platform
           AND o.shop_id  = c.shop_id
           AND o.warehouse_id IS NULL
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    # 回滚顺序：先删外键，再删列
    op.drop_constraint("fk_orders_warehouse", "orders", type_="foreignkey")
    op.drop_column("orders", "warehouse_id")
