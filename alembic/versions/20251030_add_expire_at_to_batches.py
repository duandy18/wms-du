# alembic/versions/20251030_add_expire_at_to_batches.py
"""batches: add expire_at for FEFO (idempotent)

本迁移为 FEFO（先到期先出）补充 batches.expire_at 列，并添加稳定排序索引。
考虑到部分环境可能已通过“急救 SQL”预建索引/列，本迁移在升级/回退时均做了幂等防护：
- 列/索引不存在才创建；
- 列/索引存在才删除。

Revision ID: 20251030_add_expire_at_to_batches
Revises: 20251030_add_reservations_and_v_available
Create Date: 2025-10-30
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# --- 元信息 ---
revision = "20251030_add_expire_at_to_batches"
down_revision = "20251030_add_reservations_and_v_available"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """向 batches 表新增 expire_at 列，并创建 FEFO 复合索引（幂等）"""
    conn = op.get_bind()
    insp = inspect(conn)

    # 1) 列不存在才新增
    cols = [c["name"] for c in insp.get_columns("batches")]
    if "expire_at" not in cols:
        op.add_column(
            "batches",
            sa.Column(
                "expire_at",
                sa.Date(),
                nullable=True,
                comment="到期日（FEFO）",
            ),
        )

    # 2) 索引不存在才创建（到期日 + 主键稳定二键，避免 FEFO 抖动）
    ix_exists = conn.exec_driver_sql(
        """
        SELECT 1
        FROM pg_indexes
        WHERE schemaname = 'public' AND indexname = 'ix_batches_fefo'
        LIMIT 1
        """
    ).scalar()
    if not ix_exists:
        op.create_index(
            "ix_batches_fefo",
            "batches",
            ["item_id", "warehouse_id", "location_id", "expire_at", "id"],
            unique=False,
        )


def downgrade() -> None:
    """幂等回退：存在则删除索引与列"""
    conn = op.get_bind()

    # 1) 先安全删除索引（若存在）
    ix_exists = conn.exec_driver_sql(
        """
        SELECT 1
        FROM pg_indexes
        WHERE schemaname = 'public' AND indexname = 'ix_batches_fefo'
        LIMIT 1
        """
    ).scalar()
    if ix_exists:
        op.drop_index("ix_batches_fefo", table_name="batches")

    # 2) 再安全删除列（若存在）
    insp = inspect(conn)
    cols = [c["name"] for c in insp.get_columns("batches")]
    if "expire_at" in cols:
        op.drop_column("batches", "expire_at")
