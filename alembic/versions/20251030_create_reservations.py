"""reservations: create table for batch-level reservations (idempotent)

Revision ID: 20251030_create_reservations
Revises: 20251030_orders_updated_at_default_now
Create Date: 2025-10-30
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# ---- Alembic identifiers ----
revision = "20251030_create_reservations"
down_revision = "20251030_orders_updated_at_default_now"
branch_labels = None
depends_on = None


# ---------------- helpers: idempotent checks ----------------
def _insp():
    bind = op.get_bind()
    return sa.inspect(bind)

def _has_table(name: str) -> bool:
    return _insp().has_table(name)

def _has_index(table: str, name: str) -> bool:
    try:
        return any(ix["name"] == name for ix in _insp().get_indexes(table))
    except Exception:
        return False

def _has_fk(table: str, name: str) -> bool:
    try:
        return any(fk["name"] == name for fk in _insp().get_foreign_keys(table))
    except Exception:
        return False


def upgrade() -> None:
    if not _has_table("reservations"):
        op.create_table(
            "reservations",
            sa.Column("id", sa.BigInteger, primary_key=True),
            sa.Column("order_id", sa.BigInteger, nullable=True),
            sa.Column("item_id", sa.BigInteger, nullable=False),
            sa.Column("batch_id", sa.BigInteger, nullable=True),
            sa.Column("qty", sa.Numeric(18, 6), nullable=False),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        )

    # 常用索引（幂等）
    if not _has_index("reservations", "ix_reservations_order_id"):
        op.create_index("ix_reservations_order_id", "reservations", ["order_id"], unique=False)
    if not _has_index("reservations", "ix_reservations_item_id"):
        op.create_index("ix_reservations_item_id", "reservations", ["item_id"], unique=False)
    if not _has_index("reservations", "ix_reservations_batch_id"):
        op.create_index("ix_reservations_batch_id", "reservations", ["batch_id"], unique=False)

    # 历史上可能创建过这个组合索引，保持向前兼容（幂等）
    if not _has_index("reservations", "ix_reservations_item_batch"):
        op.create_index("ix_reservations_item_batch", "reservations", ["item_id", "batch_id"], unique=False)

    # 外键（如需要，注意先判定存在性）
    if not _has_fk("reservations", "fk_reservations_item"):
        op.create_foreign_key("fk_reservations_item", "reservations", "items", ["item_id"], ["id"], onupdate="RESTRICT", ondelete="RESTRICT")
    # 其它外键按你的需要增加（例如 batch_id -> batches.id / order_id -> orders.id），这里略


def downgrade() -> None:
    # 1) 幂等删除索引（存在才删；若历史命名差异，用 IF EXISTS 兜底）
    if _has_index("reservations", "ix_reservations_item_batch"):
        op.drop_index("ix_reservations_item_batch", table_name="reservations")
    else:
        # 某些历史路径索引可能不存在；这里用 IF EXISTS 防止报错
        op.execute(sa.text("DROP INDEX IF EXISTS public.ix_reservations_item_batch"))

    if _has_index("reservations", "ix_reservations_batch_id"):
        op.drop_index("ix_reservations_batch_id", table_name="reservations")
    else:
        op.execute(sa.text("DROP INDEX IF EXISTS public.ix_reservations_batch_id"))

    if _has_index("reservations", "ix_reservations_item_id"):
        op.drop_index("ix_reservations_item_id", table_name="reservations")
    else:
        op.execute(sa.text("DROP INDEX IF EXISTS public.ix_reservations_item_id"))

    if _has_index("reservations", "ix_reservations_order_id"):
        op.drop_index("ix_reservations_order_id", table_name="reservations")
    else:
        op.execute(sa.text("DROP INDEX IF EXISTS public.ix_reservations_order_id"))

    # 2) 外键（如升级时创建过，这里按名删除；不存在就跳过）
    try:
        op.drop_constraint("fk_reservations_item", "reservations", type_="foreignkey")
    except Exception:
        pass

    # 3) 最后删除表（存在才删）
    if _has_table("reservations"):
        op.drop_table("reservations")
