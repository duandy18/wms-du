"""p42_add_trace_id_to_orders_outbound_audit

Revision ID: 6b6ad93cf221
Revises: d42d5c693371
Create Date: 2025-11-16 08:47:07.941111

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "6b6ad93cf221"
down_revision: Union[str, Sequence[str], None] = "d42d5c693371"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_trace_id_column(table: str) -> None:
    """给指定表加 trace_id 列（如果不存在）"""
    op.add_column(
        table,
        sa.Column("trace_id", sa.String(length=64), nullable=True),
    )


def upgrade() -> None:
    """给 orders / outbound_commits / audit_events 补充 trace_id 列并回填。"""

    # ------------------------------------------------------------------
    # 1) orders.trace_id
    # ------------------------------------------------------------------
    _add_trace_id_column("orders")

    # 用 external_order_id 回填初始 trace_id（如果该列存在）
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                  FROM information_schema.columns
                 WHERE table_schema = 'public'
                   AND table_name   = 'orders'
                   AND column_name  = 'external_order_id'
            ) THEN
                UPDATE orders
                   SET trace_id = external_order_id
                 WHERE trace_id IS NULL;
            END IF;
        END$$;
        """
    )

    op.create_index(
        "ix_orders_trace_id",
        "orders",
        ["trace_id"],
    )

    # ------------------------------------------------------------------
    # 2) outbound_commits.trace_id
    # ------------------------------------------------------------------
    _add_trace_id_column("outbound_commits")

    # 用 order_ref 回填初始 trace_id（如果该列存在）
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                  FROM information_schema.columns
                 WHERE table_schema = 'public'
                   AND table_name   = 'outbound_commits'
                   AND column_name  = 'order_ref'
            ) THEN
                UPDATE outbound_commits
                   SET trace_id = order_ref
                 WHERE trace_id IS NULL;
            END IF;
        END$$;
        """
    )

    op.create_index(
        "ix_outbound_commits_trace_id",
        "outbound_commits",
        ["trace_id"],
    )

    # ------------------------------------------------------------------
    # 3) audit_events.trace_id
    # ------------------------------------------------------------------
    _add_trace_id_column("audit_events")

    # 用 ref 回填初始 trace_id（如果该列存在）
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                  FROM information_schema.columns
                 WHERE table_schema = 'public'
                   AND table_name   = 'audit_events'
                   AND column_name  = 'ref'
            ) THEN
                UPDATE audit_events
                   SET trace_id = ref
                 WHERE trace_id IS NULL;
            END IF;
        END$$;
        """
    )

    op.create_index(
        "ix_audit_events_trace_id",
        "audit_events",
        ["trace_id"],
    )


def downgrade() -> None:
    """回滚：删除 trace_id 索引和列。"""

    # audit_events
    op.drop_index("ix_audit_events_trace_id", table_name="audit_events")
    op.drop_column("audit_events", "trace_id")

    # outbound_commits
    op.drop_index("ix_outbound_commits_trace_id", table_name="outbound_commits")
    op.drop_column("outbound_commits", "trace_id")

    # orders
    op.drop_index("ix_orders_trace_id", table_name="orders")
    op.drop_column("orders", "trace_id")
