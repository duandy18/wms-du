"""unify time columns to timestamptz

Revision ID: 391c76dee630
Revises: p38_20251113_reservations_soft_unique
Create Date: 2025-11-15 22:53:37.481120

本迁移的目标：
- 将核心表中的时间列统一为 timestamptz（UTC 语义）；
- 后续所有 TTL / trace / 审计逻辑都在 UTC 维度上工作。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "391c76dee630"
down_revision: Union[str, Sequence[str], None] = "p38_20251113_reservations_soft_unique"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _alter_ts_to_timestamptz(table: str, column: str) -> None:
    """
    如果指定表/列存在且类型为 timestamp without time zone，
    则将其转换为 timestamptz（按 UTC 解释原始值）。
    """
    sql = f"""
    DO $$
    BEGIN
        IF EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = '{table}'
              AND column_name = '{column}'
              AND data_type = 'timestamp without time zone'
        ) THEN
            ALTER TABLE {table}
                ALTER COLUMN {column}
                TYPE timestamptz
                USING {column} AT TIME ZONE 'UTC';
        END IF;
    END
    $$;
    """
    op.execute(sa.text(sql))


def _alter_timestamptz_to_ts(table: str, column: str) -> None:
    """
    反向迁移：如果列是 timestamptz，则降级回 timestamp without time zone。
    注意：这会丢掉时区信息，但在我们约定“全部当作 UTC”的前提下影响可接受。
    """
    sql = f"""
    DO $$
    BEGIN
        IF EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = '{table}'
              AND column_name = '{column}'
              AND data_type = 'timestamp with time zone'
        ) THEN
            ALTER TABLE {table}
                ALTER COLUMN {column}
                TYPE timestamp
                USING {column} AT TIME ZONE 'UTC';
        END IF;
    END
    $$;
    """
    op.execute(sa.text(sql))


def upgrade() -> None:
    """Upgrade schema: unify time columns to timestamptz (UTC)."""

    # --- reservations: 头表生命周期 + TTL ---
    _alter_ts_to_timestamptz("reservations", "created_at")
    _alter_ts_to_timestamptz("reservations", "updated_at")
    _alter_ts_to_timestamptz("reservations", "expire_at")

    # --- reservation_lines: 明细行时间 ---
    _alter_ts_to_timestamptz("reservation_lines", "created_at")
    _alter_ts_to_timestamptz("reservation_lines", "updated_at")

    # --- stock_ledger: 核心库存流水时间 ---
    _alter_ts_to_timestamptz("stock_ledger", "created_at")

    # --- snapshots: 快照生成 / 更新时间 ---
    _alter_ts_to_timestamptz("snapshots", "created_at")
    _alter_ts_to_timestamptz("snapshots", "updated_at")

    # --- event_store: 平台 / 内部事件落库时间 ---
    _alter_ts_to_timestamptz("event_store", "created_at")

    # --- audit_events: 审计事件时间 ---
    _alter_ts_to_timestamptz("audit_events", "created_at")


def downgrade() -> None:
    """Downgrade schema: revert time columns back to timestamp (without tz)."""

    # 反向顺序执行，逻辑对称即可

    # --- audit_events / event_store ---
    _alter_timestamptz_to_ts("audit_events", "created_at")
    _alter_timestamptz_to_ts("event_store", "created_at")

    # --- snapshots ---
    _alter_timestamptz_to_ts("snapshots", "updated_at")
    _alter_timestamptz_to_ts("snapshots", "created_at")

    # --- stock_ledger ---
    _alter_timestamptz_to_ts("stock_ledger", "created_at")

    # --- reservation_lines ---
    _alter_timestamptz_to_ts("reservation_lines", "updated_at")
    _alter_timestamptz_to_ts("reservation_lines", "created_at")

    # --- reservations ---
    _alter_timestamptz_to_ts("reservations", "expire_at")
    _alter_timestamptz_to_ts("reservations", "updated_at")
    _alter_timestamptz_to_ts("reservations", "created_at")
