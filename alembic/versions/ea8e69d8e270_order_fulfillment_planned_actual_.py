"""order_fulfillment planned actual warehouses (one-shot)

Revision ID: ea8e69d8e270
Revises: e28d90453401
Create Date: 2026-02-04 13:56:04.473295

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "ea8e69d8e270"
down_revision: Union[str, Sequence[str], None] = "e28d90453401"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    一步到位（无过渡期同步）：

    0) 处理依赖对象：vw_routing_metrics_daily 依赖 orders.warehouse_id，先 drop，最后重建
    1) 新建 1:1 附属表 order_fulfillment，承载 planned/actual + 履约快照
    2) Backfill：从 orders 现有列回填到 order_fulfillment
    3) 从 orders 删除这些列（仓库/履约相关列整体“单列出来”）
    4) 重建 vw_routing_metrics_daily：warehouse_id 改为来自 order_fulfillment.actual_warehouse_id
    """

    # 0) drop dependent view first
    op.execute("DROP VIEW IF EXISTS vw_routing_metrics_daily;")

    # 1) create order_fulfillment
    op.create_table(
        "order_fulfillment",
        sa.Column(
            "order_id",
            sa.BigInteger(),
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        # planned / actual（你定的“计划/实际”）
        sa.Column(
            "planned_warehouse_id",
            sa.Integer(),
            sa.ForeignKey("warehouses.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "actual_warehouse_id",
            sa.Integer(),
            sa.ForeignKey("warehouses.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        # 履约快照（先照搬旧列；后续你再减肥/停写/删除都行）
        sa.Column("fulfillment_status", sa.String(length=32), nullable=True),
        sa.Column("blocked_reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("blocked_detail", sa.Text(), nullable=True),
        sa.Column("overridden_by", sa.Integer(), nullable=True),
        sa.Column("overridden_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("override_reason", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_order_fulfillment_planned_wh", "order_fulfillment", ["planned_warehouse_id"])
    op.create_index("ix_order_fulfillment_actual_wh", "order_fulfillment", ["actual_warehouse_id"])
    op.create_index("ix_order_fulfillment_status", "order_fulfillment", ["fulfillment_status"])

    # 2) backfill from orders
    op.execute(
        """
        INSERT INTO order_fulfillment(
            order_id,
            planned_warehouse_id,
            actual_warehouse_id,
            fulfillment_status,
            blocked_reasons,
            blocked_detail,
            overridden_by,
            overridden_at,
            override_reason,
            updated_at
        )
        SELECT
            o.id AS order_id,
            o.service_warehouse_id AS planned_warehouse_id,
            o.warehouse_id AS actual_warehouse_id,
            o.fulfillment_status,
            o.blocked_reasons,
            o.blocked_detail,
            o.overridden_by,
            o.overridden_at,
            o.override_reason,
            now() AS updated_at
        FROM orders o
        ON CONFLICT (order_id) DO NOTHING
        """
    )

    # 3) drop old columns on orders (one-shot)
    # drop FK constraint on orders.warehouse_id first (name from your \\d orders)
    op.drop_constraint("fk_orders_warehouse", "orders", type_="foreignkey")

    with op.batch_alter_table("orders") as batch_op:
        batch_op.drop_column("fulfillment_warehouse_id")
        batch_op.drop_column("warehouse_id")
        batch_op.drop_column("service_warehouse_id")
        batch_op.drop_column("fulfillment_status")
        batch_op.drop_column("blocked_detail")
        batch_op.drop_column("blocked_reasons")
        batch_op.drop_column("overridden_by")
        batch_op.drop_column("overridden_at")
        batch_op.drop_column("override_reason")

    # 4) recreate vw_routing_metrics_daily using order_fulfillment.actual_warehouse_id
    # keep output column name warehouse_id for backward compatibility
    op.execute(
        """
        CREATE VIEW vw_routing_metrics_daily AS
        SELECT
            date_trunc('day'::text, o.created_at) AS day,
            o.platform,
            o.shop_id,
            COALESCE(s.route_mode, 'FALLBACK'::character varying) AS route_mode,
            f.actual_warehouse_id AS warehouse_id,
            count(*) FILTER (WHERE f.actual_warehouse_id IS NOT NULL) AS routed_orders,
            count(*) FILTER (WHERE f.actual_warehouse_id IS NULL) AS failed_orders
        FROM orders o
        LEFT JOIN order_fulfillment f ON f.order_id = o.id
        LEFT JOIN stores s ON s.platform::text = o.platform::text AND s.shop_id::text = o.shop_id::text
        GROUP BY
            date_trunc('day'::text, o.created_at),
            o.platform,
            o.shop_id,
            COALESCE(s.route_mode, 'FALLBACK'::character varying),
            f.actual_warehouse_id;
        """
    )


def downgrade() -> None:
    """
    回滚：
    0) 先 drop 新版 view（它依赖 order_fulfillment）
    1) 把 orders 的列加回去
    2) 从 order_fulfillment 回填到 orders
    3) 恢复 orders.warehouse_id 外键
    4) 重建旧版 view（依赖 orders.warehouse_id）
    5) 再删 order_fulfillment 表
    """

    # 0) drop view first (depends on order_fulfillment)
    op.execute("DROP VIEW IF EXISTS vw_routing_metrics_daily;")

    # 1) add columns back to orders
    with op.batch_alter_table("orders") as batch_op:
        batch_op.add_column(sa.Column("override_reason", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("overridden_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("overridden_by", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("blocked_reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
        batch_op.add_column(sa.Column("blocked_detail", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("fulfillment_status", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("service_warehouse_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("warehouse_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("fulfillment_warehouse_id", sa.Integer(), nullable=True))

    # 2) backfill orders from order_fulfillment
    op.execute(
        """
        UPDATE orders o
           SET service_warehouse_id = f.planned_warehouse_id,
               warehouse_id = f.actual_warehouse_id,
               fulfillment_status = f.fulfillment_status,
               blocked_reasons = f.blocked_reasons,
               blocked_detail = f.blocked_detail,
               overridden_by = f.overridden_by,
               overridden_at = f.overridden_at,
               override_reason = f.override_reason
          FROM order_fulfillment f
         WHERE f.order_id = o.id
        """
    )

    # 3) restore FK constraint on orders.warehouse_id
    op.create_foreign_key(
        "fk_orders_warehouse",
        "orders",
        "warehouses",
        ["warehouse_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # 4) recreate old view using orders.warehouse_id
    op.execute(
        """
        CREATE VIEW vw_routing_metrics_daily AS
        SELECT
            date_trunc('day'::text, o.created_at) AS day,
            o.platform,
            o.shop_id,
            COALESCE(s.route_mode, 'FALLBACK'::character varying) AS route_mode,
            o.warehouse_id,
            count(*) FILTER (WHERE o.warehouse_id IS NOT NULL) AS routed_orders,
            count(*) FILTER (WHERE o.warehouse_id IS NULL) AS failed_orders
        FROM orders o
        LEFT JOIN stores s ON s.platform::text = o.platform::text AND s.shop_id::text = o.shop_id::text
        GROUP BY
            date_trunc('day'::text, o.created_at),
            o.platform,
            o.shop_id,
            COALESCE(s.route_mode, 'FALLBACK'::character varying),
            o.warehouse_id;
        """
    )

    # 5) drop order_fulfillment
    op.drop_index("ix_order_fulfillment_status", table_name="order_fulfillment")
    op.drop_index("ix_order_fulfillment_actual_wh", table_name="order_fulfillment")
    op.drop_index("ix_order_fulfillment_planned_wh", table_name="order_fulfillment")
    op.drop_table("order_fulfillment")
