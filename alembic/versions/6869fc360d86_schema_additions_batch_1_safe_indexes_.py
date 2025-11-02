"""schema additions batch-1 (safe indexes only)

Revision ID: 6869fc360d86
Revises: 6077053642c5
Create Date: 2025-10-29 19:10:00
"""
from alembic import op
import sqlalchemy as sa

revision = "6869fc360d86"
down_revision = "6077053642c5"  # 按你的 heads -v：当前 head 是 6077053642c5
branch_labels = None
depends_on = None


def upgrade():
    # 仅做“只增不删”的关键索引；全部幂等（IF NOT EXISTS）
    # 1) order_items：常用过滤条件
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_order_items_order_id ON public.order_items (order_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_order_items_item_id ON public.order_items (item_id)"
    ))

    # 2) items：SKU 唯一 & 点查
    op.execute(sa.text(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_items_sku ON public.items (sku)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_items_id ON public.items (id)"
    ))

    # 3) locations：按仓维度查库位
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_locations_warehouse_id ON public.locations (warehouse_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_locations_wh ON public.locations (warehouse_id)"
    ))

    # 4) batches：FEFO 与维度过滤常用
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_batches_item_id ON public.batches (item_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_batches_location_id ON public.batches (location_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_batches_warehouse_id ON public.batches (warehouse_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_batches_expiry_date ON public.batches (expiry_date)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_batches_expiry ON public.batches (expiry_date)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_batches_batch_code ON public.batches (batch_code)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_batches_code ON public.batches (batch_code)"
    ))

    # 5) channel_inventory：店+货的可见量与占用
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_channel_inventory_item_id ON public.channel_inventory (item_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_channel_inventory_store_id ON public.channel_inventory (store_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_channel_inventory_store_item "
        "ON public.channel_inventory (store_id, item_id)"
    ))

    # 6) stock_snapshots：快照维度（仅新增索引，不触碰列与约束）
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_stock_snapshots_batch_id ON public.stock_snapshots (batch_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_stock_snapshots_item_id ON public.stock_snapshots (item_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_stock_snapshots_location_id ON public.stock_snapshots (location_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_stock_snapshots_snapshot_date ON public.stock_snapshots (snapshot_date)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_stock_snapshots_warehouse_id ON public.stock_snapshots (warehouse_id)"
    ))

    # 7) stock_ledger：四列唯一键（若你的现库暂无该唯一索引，这里不强加）
    op.execute(sa.text(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_ledger_reason_ref_refline_stock "
        "ON public.stock_ledger (reason, ref, ref_line, stock_id)"
    ))


def downgrade():
    # 幂等删除这些索引（不会删除表/外键/数据）
    op.execute(sa.text("DROP INDEX IF EXISTS public.ix_order_items_order_id"))
    op.execute(sa.text("DROP INDEX IF EXISTS public.ix_order_items_item_id"))

    op.execute(sa.text("DROP INDEX IF EXISTS public.ix_items_sku"))
    op.execute(sa.text("DROP INDEX IF EXISTS public.ix_items_id"))

    op.execute(sa.text("DROP INDEX IF EXISTS public.ix_locations_warehouse_id"))
    op.execute(sa.text("DROP INDEX IF EXISTS public.ix_locations_wh"))

    op.execute(sa.text("DROP INDEX IF EXISTS public.ix_batches_item_id"))
    op.execute(sa.text("DROP INDEX IF EXISTS public.ix_batches_location_id"))
    op.execute(sa.text("DROP INDEX IF EXISTS public.ix_batches_warehouse_id"))
    op.execute(sa.text("DROP INDEX IF EXISTS public.ix_batches_expiry_date"))
    op.execute(sa.text("DROP INDEX IF EXISTS public.ix_batches_expiry"))
    op.execute(sa.text("DROP INDEX IF EXISTS public.ix_batches_batch_code"))
    op.execute(sa.text("DROP INDEX IF EXISTS public.ix_batches_code"))

    op.execute(sa.text("DROP INDEX IF EXISTS public.ix_channel_inventory_item_id"))
    op.execute(sa.text("DROP INDEX IF EXISTS public.ix_channel_inventory_store_id"))
    op.execute(sa.text("DROP INDEX IF EXISTS public.ix_channel_inventory_store_item"))

    op.execute(sa.text("DROP INDEX IF EXISTS public.ix_stock_snapshots_batch_id"))
    op.execute(sa.text("DROP INDEX IF EXISTS public.ix_stock_snapshots_item_id"))
    op.execute(sa.text("DROP INDEX IF EXISTS public.ix_stock_snapshots_location_id"))
    op.execute(sa.text("DROP INDEX IF EXISTS public.ix_stock_snapshots_snapshot_date"))
    op.execute(sa.text("DROP INDEX IF EXISTS public.ix_stock_snapshots_warehouse_id"))

    op.execute(sa.text("DROP INDEX IF EXISTS public.uq_ledger_reason_ref_refline_stock"))
