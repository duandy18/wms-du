"""reservations + v_available view (idempotent & CI-safe)

Revision ID: 20251030_add_reservations_and_v_available
Revises: bf539dde5f39
Create Date: 2025-10-30 10:20:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20251030_add_reservations_and_v_available"
down_revision = "bf539dde5f39"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1) reservations 表（幂等）
    conn.execute(sa.text("""
    CREATE TABLE IF NOT EXISTS public.reservations (
      id BIGSERIAL PRIMARY KEY,
      item_id BIGINT NOT NULL,
      location_id BIGINT NOT NULL,
      qty NUMERIC(18,6) NOT NULL,
      status TEXT NOT NULL DEFAULT 'ACTIVE',
      ref TEXT NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """))

    # 2) 唯一索引（幂等）——注意：唯一索引(带 WHERE)
    conn.execute(sa.text("""
    CREATE UNIQUE INDEX IF NOT EXISTS uq_reserve_idem
      ON public.reservations (ref, item_id, location_id)
      WHERE status='ACTIVE';
    """))

    # 3) 常用索引（幂等）
    conn.execute(sa.text("""
    CREATE INDEX IF NOT EXISTS idx_reservations_active_i_l
      ON public.reservations (item_id, location_id)
      WHERE status='ACTIVE';
    """))
    conn.execute(sa.text("""
    CREATE INDEX IF NOT EXISTS idx_stocks_i_l
      ON public.stocks (item_id, location_id);
    """))

    # 4) 只读视图（幂等替换）
    conn.execute(sa.text("""
    CREATE OR REPLACE VIEW public.v_available AS
    WITH s AS (
      SELECT item_id, location_id, SUM(qty) AS on_hand
        FROM public.stocks
       GROUP BY 1,2
    ),
    r AS (
      SELECT item_id, location_id, SUM(qty) AS reserved
        FROM public.reservations
       WHERE status='ACTIVE'
       GROUP BY 1,2
    )
    SELECT
      COALESCE(s.item_id, r.item_id) AS item_id,
      COALESCE(s.location_id, r.location_id) AS location_id,
      COALESCE(s.on_hand, 0) AS on_hand,
      COALESCE(r.reserved, 0) AS reserved,
      COALESCE(s.on_hand, 0) - COALESCE(r.reserved, 0) AS available
    FROM s
    FULL JOIN r USING (item_id, location_id);
    """))


def downgrade() -> None:
    conn = op.get_bind()

    # 先删视图 → 再删索引 → 再删表（幂等）
    conn.execute(sa.text("DROP VIEW IF EXISTS public.v_available"))
    conn.execute(sa.text("DROP INDEX IF EXISTS public.idx_reservations_active_i_l"))
    conn.execute(sa.text("DROP INDEX IF EXISTS public.uq_reserve_idem"))
    conn.execute(sa.text("DROP TABLE IF EXISTS public.reservations"))
