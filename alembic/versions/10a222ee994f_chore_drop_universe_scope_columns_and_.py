"""chore: drop universe scope columns and rebuild uniques

Revision ID: 10a222ee994f
Revises: 991408f97d6d
Create Date: 2026-02-14 01:50:02.852554

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "10a222ee994f"
down_revision: Union[str, Sequence[str], None] = "991408f97d6d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Drop universe scope (PROD/DRILL) columns and rebuild unique constraints
    without scope dimension.

    Notes:
    - pricing_scheme_dest_adjustments.scope is geo-scope (province/city). Do NOT touch.
    - store_tokens.scope is OAuth scope string. Do NOT touch.
    - Use IF EXISTS to tolerate DEV/TEST drift in constraint/index names.
    """
    conn = op.get_bind()

    # -------------------------
    # orders
    # -------------------------
    conn.execute(sa.text("ALTER TABLE orders DROP CONSTRAINT IF EXISTS uq_orders_platform_shop_ext"))
    conn.execute(
        sa.text(
            "ALTER TABLE orders ADD CONSTRAINT uq_orders_platform_shop_ext "
            "UNIQUE (platform, shop_id, ext_order_no)"
        )
    )
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_orders_scope_platform_shop"))
    conn.execute(sa.text("ALTER TABLE orders DROP COLUMN IF EXISTS scope"))

    # -------------------------
    # outbound_commits_v2
    # -------------------------
    conn.execute(
        sa.text(
            "ALTER TABLE outbound_commits_v2 DROP CONSTRAINT IF EXISTS uq_outbound_commits_v2_platform_shop_ref"
        )
    )
    conn.execute(
        sa.text(
            "ALTER TABLE outbound_commits_v2 ADD CONSTRAINT uq_outbound_commits_v2_platform_shop_ref "
            "UNIQUE (platform, shop_id, ref)"
        )
    )
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_outbound_commits_v2_scope_trace_id"))
    conn.execute(sa.text("ALTER TABLE outbound_commits_v2 DROP COLUMN IF EXISTS scope"))

    # -------------------------
    # pick_tasks
    # -------------------------
    # DEV/TEST 可能是 UNIQUE CONSTRAINT，也可能是 UNIQUE INDEX。两种都兜住。
    conn.execute(sa.text("ALTER TABLE pick_tasks DROP CONSTRAINT IF EXISTS uq_pick_tasks_ref_wh"))
    conn.execute(sa.text("DROP INDEX IF EXISTS uq_pick_tasks_ref_wh"))
    # 也可能被创建成别名约束/索引（保守兜底：删 scope 相关索引）
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_pick_tasks_scope_status"))
    conn.execute(sa.text("ALTER TABLE pick_tasks DROP COLUMN IF EXISTS scope"))
    # 重建唯一键（无 scope）
    conn.execute(
        sa.text(
            "ALTER TABLE pick_tasks ADD CONSTRAINT uq_pick_tasks_ref_wh "
            "UNIQUE (ref, warehouse_id)"
        )
    )

    # -------------------------
    # platform_order_addresses
    # -------------------------
    conn.execute(
        sa.text(
            "ALTER TABLE platform_order_addresses DROP CONSTRAINT IF EXISTS uq_po_addr_scope_platform_store_ext"
        )
    )
    conn.execute(
        sa.text(
            "ALTER TABLE platform_order_addresses ADD CONSTRAINT uq_po_addr_scope_platform_store_ext "
            "UNIQUE (platform, store_id, ext_order_no)"
        )
    )
    conn.execute(sa.text("ALTER TABLE platform_order_addresses DROP COLUMN IF EXISTS scope"))

    # -------------------------
    # stock_ledger
    # -------------------------
    conn.execute(
        sa.text(
            "ALTER TABLE stock_ledger DROP CONSTRAINT IF EXISTS uq_ledger_wh_batch_item_reason_ref_line"
        )
    )
    conn.execute(
        sa.text(
            "ALTER TABLE stock_ledger ADD CONSTRAINT uq_ledger_wh_batch_item_reason_ref_line "
            "UNIQUE (reason, ref, ref_line, item_id, batch_code_key, warehouse_id)"
        )
    )
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_stock_ledger_scope_dims"))
    conn.execute(sa.text("ALTER TABLE stock_ledger DROP COLUMN IF EXISTS scope"))

    # -------------------------
    # stock_snapshots
    # -------------------------
    conn.execute(sa.text("ALTER TABLE stock_snapshots DROP CONSTRAINT IF EXISTS uq_stock_snapshot_grain_v2"))
    conn.execute(
        sa.text(
            "ALTER TABLE stock_snapshots ADD CONSTRAINT uq_stock_snapshot_grain_v2 "
            "UNIQUE (snapshot_date, warehouse_id, item_id, batch_code_key)"
        )
    )
    conn.execute(sa.text("ALTER TABLE stock_snapshots DROP COLUMN IF EXISTS scope"))

    # -------------------------
    # stocks
    # -------------------------
    conn.execute(sa.text("ALTER TABLE stocks DROP CONSTRAINT IF EXISTS uq_stocks_item_wh_batch"))
    conn.execute(
        sa.text(
            "ALTER TABLE stocks ADD CONSTRAINT uq_stocks_item_wh_batch "
            "UNIQUE (item_id, warehouse_id, batch_code_key)"
        )
    )
    conn.execute(sa.text("ALTER TABLE stocks DROP COLUMN IF EXISTS scope"))


def downgrade() -> None:
    raise RuntimeError("Irreversible migration: universe scope columns and constraints were dropped.")
