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

def _has_column(table: str, column: str) -> bool:
    try:
        return any(c["name"] == column for c in _insp().get_columns(table))
    except Exception:
        return False


def upgrade() -> None:
    # 1) 表不存在则创建（标准形态）
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
    else:
        # 2) 表已存在：逐列补齐缺失列（幂等）
        if not _has_column("reservations", "order_id"):
            op.add_column("reservations", sa.Column("order_id", sa.BigInteger, nullable=True))
        if not _has_column("reservations", "item_id"):
            op.add_column("reservations", sa.Column("item_id", sa.BigInteger, nullable=False))
        if not _has_column("reservations", "batch_id"):
            op.add_column("reservations", sa.Column("batch_id", sa.BigInteger, nullable=True))
        if not _has_column("reservations", "qty"):
            op.add_column("reservations", sa.Column("qty", sa.Numeric(18, 6), nullable=False, server_default=sa.text("0")))
            op.alter_column("reservations", "qty", server_default=None)
        if not _has_column("reservations", "created_at"):
            op.add_column(
                "reservations",
                sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
            )

    # 3) 仅对存在的列创建索引（幂等）
    if _has_column("reservations", "order_id") and not _has_index("reservations", "ix_reservations_order_id"):
        op.create_index("ix_reservations_order_id", "reservations", ["order_id"], unique=False)

    if _has_column("reservations", "item_id") and not _has_index("reservations", "ix_reservations_item_id"):
        op.create_index("ix_reservations_item_id", "reservations", ["item_id"], unique=False)

    if _has_column("reservations", "batch_id") and not _has_index("reservations", "ix_reservations_batch_id"):
        op.create_index("ix_reservations_batch_id", "reservations", ["batch_id"], unique=False)

    # 历史兼容：如曾创建过组合索引（item_id,batch_id），确保存在；否则跳过
    if (
        _has_column("reservations", "item_id")
        and _has_column("reservations", "batch_id")
        and not _has_index("reservations", "ix_reservations_item_batch")
    ):
        op.create_index("ix_reservations_item_batch", "reservations", ["item_id", "batch_id"], unique=False)

    # 4) 外键（如需要；按需开启）
    # if _has_column("reservations", "item_id") and not _has_fk("reservations", "fk_reservations_item"):
    #     op.create_foreign_key("fk_reservations_item", "reservations", "items",
    #                           ["item_id"], ["id"], onupdate="RESTRICT", ondelete="RESTRICT")
    # if _has_column("reservations", "batch_id") and not _has_fk("reservations", "fk_reservations_batch"):
    #     op.create_foreign_key("fk_reservations_batch", "reservations", "batches",
    #                           ["batch_id"], ["id"], onupdate="RESTRICT", ondelete="SET NULL")
    # if _has_column("reservations", "order_id") and not _has_fk("reservations", "fk_reservations_order"):
    #     op.create_foreign_key("fk_reservations_order", "reservations", "orders",
    #                           ["order_id"], ["id"], onupdate="RESTRICT", ondelete="SET NULL")


def downgrade() -> None:
    # 幂等删除索引（存在才删；否则用 IF EXISTS 兜底）
    if _has_index("reservations", "ix_reservations_item_batch"):
        op.drop_index("ix_reservations_item_batch", table_name="reservations")
    else:
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

    # 外键删除（若升级时创建过）
    try:
        op.drop_constraint("fk_reservations_item", "reservations", type_="foreignkey")
    except Exception:
        pass
    try:
        op.drop_constraint("fk_reservations_batch", "reservations", type_="foreignkey")
    except Exception:
        pass
    try:
        op.drop_constraint("fk_reservations_order", "reservations", type_="foreignkey")
    except Exception:
        pass

    # 最后删除表（存在才删）
    if _has_table("reservations"):
        op.drop_table("reservations")
