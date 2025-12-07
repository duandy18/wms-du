"""Rewrite v_putaway_ledger_recent to use v_stocks_enriched instead of stocks

This creates a helper view v_stocks_enriched that exposes:
  - item_id, location_id, batch_id, qty
  - batch_code      (from batches)
  - warehouse_id    (from locations)

Then it rewrites v_putaway_ledger_recent to reference v_stocks_enriched
so that downstream code can still use columns named `batch_code` and
`warehouse_id` without depending on legacy columns in `stocks`.

Revision ID: 20251104_rewrite_v_putaway_ledger_recent
Revises: 20251104_cleanup_stocks_drop_legacy_cols
Create Date: 2025-11-04 22:40:00
"""

from __future__ import annotations

import re
from typing import Optional, Sequence

from alembic import op
import sqlalchemy as sa

# ---- Alembic identifiers ----
revision: str = "20251104_rewrite_v_putaway_ledger_recent"
down_revision: Optional[str] = "20251104_cleanup_stocks_drop_legacy_cols"
branch_labels: Optional[Sequence[str]] = None
depends_on: Optional[Sequence[str]] = None
# -----------------------------


def upgrade():
    conn = op.get_bind()

    # 1) Helper view: v_stocks_enriched
    #    将旧来从 stocks 直接取的 batch_code / warehouse_id，改为从 batches/locations 推导
    conn.execute(
        sa.text("""
        CREATE OR REPLACE VIEW v_stocks_enriched AS
        SELECT
            s.id          AS id,
            s.item_id     AS item_id,
            s.location_id AS location_id,
            s.batch_id    AS batch_id,
            s.qty         AS qty,
            b.batch_code  AS batch_code,
            loc.warehouse_id AS warehouse_id
        FROM stocks s
        JOIN batches  b   ON b.id = s.batch_id
        JOIN locations loc ON loc.id = s.location_id
    """)
    )

    # 2) 动态重写 v_putaway_ledger_recent 的定义：
    #    把所有对 "stocks" 的表引用统一替换为 "v_stocks_enriched"
    #    这避免我们必须知道旧视图的完整列清单与 JOIN 结构
    #    注意：仅在视图存在时重写；如果不存在则跳过
    res = conn.execute(
        sa.text("""
        SELECT to_regclass('public.v_putaway_ledger_recent') IS NOT NULL
    """)
    ).scalar_one()
    if res:
        # 获取当前视图定义（裸 SELECT），并进行规则化替换
        view_sql = conn.execute(
            sa.text("""
            SELECT pg_get_viewdef('public.v_putaway_ledger_recent'::regclass, true)
        """)
        ).scalar_one()

        # 规则：FROM/ JOIN 中对 stocks 的引用替换为 v_stocks_enriched
        # 处理带/不带 schema、带引号/不带引号的多种写法
        patterns = [
            r'(?i)\\bFROM\\s+("public"\\.)?"stocks"\\b',
            r'(?i)\\bJOIN\\s+("public"\\.)?"stocks"\\b',
        ]
        new_sql = view_sql
        for pat in patterns:
            new_sql = re.sub(
                pat, lambda m: m.group(0).lower().replace("stocks", "v_stocks_enriched"), new_sql
            )

        # 用重写后的 SELECT 来替换视图
        # pg_get_viewdef 返回的是 SELECT ...；这里拼成 CREATE OR REPLACE
        conn.execute(sa.text(f"CREATE OR REPLACE VIEW public.v_putaway_ledger_recent AS {new_sql}"))

    # 3) 附带说明：这一步之后，v_putaway_ledger_recent 再也不直接依赖 stocks.batch_code / stocks.warehouse_id
    #    而是依赖 v_stocks_enriched 的 batch_code / warehouse_id（来自 batches / locations）


def downgrade():
    conn = op.get_bind()

    # 如果存在 v_putaway_ledger_recent，就把定义替换回引用 stocks 的版本
    res = conn.execute(
        sa.text("""
        SELECT to_regclass('public.v_putaway_ledger_recent') IS NOT NULL
    """)
    ).scalar_one()
    if res:
        view_sql = conn.execute(
            sa.text("""
            SELECT pg_get_viewdef('public.v_putaway_ledger_recent'::regclass, true)
        """)
        ).scalar_one()

        # 逆向替换：把 v_stocks_enriched 改回 stocks
        patterns = [
            r'(?i)\\bFROM\\s+("public"\\.)?"v_stocks_enriched"\\b',
            r'(?i)\\bJOIN\\s+("public"\\.)?"v_stocks_enriched"\\b',
        ]
        old_sql = view_sql
        for pat in patterns:
            old_sql = re.sub(
                pat, lambda m: m.group(0).lower().replace("v_stocks_enriched", "stocks"), old_sql
            )

        conn.execute(sa.text(f"CREATE OR REPLACE VIEW public.v_putaway_ledger_recent AS {old_sql}"))

    # 删除 helper 视图
    conn.execute(sa.text("DROP VIEW IF EXISTS public.v_stocks_enriched"))
