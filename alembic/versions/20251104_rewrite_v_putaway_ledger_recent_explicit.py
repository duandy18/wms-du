"""Explicitly rewrite v_putaway_ledger_recent to use v_stocks_enriched

- Ensures helper view v_stocks_enriched exists
- Replaces v_putaway_ledger_recent to join v_stocks_enriched (not stocks)

Revision ID: 20251104_rewrite_v_putaway_ledger_recent_explicit
Revises: 20251104_cleanup_stocks_drop_legacy_cols
Create Date: 2025-11-04 23:20:00
"""

from __future__ import annotations

from typing import Optional, Sequence

from alembic import op
import sqlalchemy as sa

# ---- Alembic identifiers ----
revision: str = "20251104_rewrite_v_putaway_ledger_recent_explicit"
down_revision: Optional[str] = "20251104_cleanup_stocks_drop_legacy_cols"
branch_labels: Optional[Sequence[str]] = None
depends_on: Optional[Sequence[str]] = None
# -----------------------------


def upgrade():
    conn = op.get_bind()

    # Helper view: v_stocks_enriched  —— 提供 batch_code / warehouse_id（来自 batches / locations）
    conn.execute(
        sa.text("""
        CREATE OR REPLACE VIEW public.v_stocks_enriched AS
        SELECT
            s.id              AS id,
            s.item_id         AS item_id,
            s.location_id     AS location_id,
            s.batch_id        AS batch_id,
            s.qty             AS qty,
            b.batch_code      AS batch_code,
            loc.warehouse_id  AS warehouse_id
        FROM public.stocks s
        JOIN public.batches  b   ON b.id = s.batch_id
        JOIN public.locations loc ON loc.id = s.location_id;
    """)
    )

    # 显式改写：v_putaway_ledger_recent —— 不再引用 stocks，改为 v_stocks_enriched
    conn.execute(
        sa.text("""
        CREATE OR REPLACE VIEW public.v_putaway_ledger_recent AS
        SELECT
            l.id,
            l.occurred_at,
            l.ref,
            l.ref_line,
            l.item_id,
            l.delta::integer      AS delta,
            l.after_qty::integer  AS after_qty,
            se.warehouse_id,
            se.location_id,
            se.batch_code
        FROM public.stock_ledger l
        JOIN public.v_stocks_enriched se
          ON se.id = l.stock_id
        WHERE l.reason = 'PUTAWAY'
        ORDER BY l.id DESC;
    """)
    )


def downgrade():
    conn = op.get_bind()

    # 恢复到“直接引用 stocks”的老版本（与你当前库内视图一致）
    conn.execute(
        sa.text("""
        CREATE OR REPLACE VIEW public.v_putaway_ledger_recent AS
        SELECT
            l.id,
            l.occurred_at,
            l.ref,
            l.ref_line,
            l.item_id,
            l.delta::integer      AS delta,
            l.after_qty::integer  AS after_qty,
            s.warehouse_id,
            s.location_id,
            s.batch_code
        FROM public.stock_ledger l
        JOIN public.stocks s
          ON s.id = l.stock_id
        WHERE l.reason = 'PUTAWAY'
        ORDER BY l.id DESC;
    """)
    )

    # 可选：删除 helper 视图（若你想严格回滚）
    conn.execute(sa.text("DROP VIEW IF EXISTS public.v_stocks_enriched"))
