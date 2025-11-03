"""event_log.message -> JSONB (drop dependent views; JSONB-safe recreation for known views)

Revision ID: 7f3b9a2c4d10
Revises: c249625e0866
Create Date: 2025-11-03 13:05:00.000000
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Sequence, Tuple, Union

from alembic import op
from sqlalchemy import text
from sqlalchemy.engine import Connection, Row

# --- Alembic identifiers ---
revision: str = "7f3b9a2c4d10"
down_revision: Union[str, Sequence[str], None] = "c249625e0866"
branch_labels = None
depends_on = None

SCHEMA = "public"
TABLE = "event_log"
COL = "message"

# 已知依赖 JSON 的视图（按需补充）
KNOWN_JSON_VIEWS = {"v_scan_trace", "v_scan_recent"}


def _q(ident: str) -> str:
    return '"' + ident.replace('"', '""') + '"'


def _dep_views(conn: Connection) -> List[Tuple[str, str, str]]:
    """
    返回依赖 public.event_log.message 的视图 (schema, name, definition)
    """
    sql = f"""
        SELECT n.nspname AS schema_name,
               c.relname AS view_name,
               pg_get_viewdef(c.oid, true) AS definition
          FROM pg_depend d
          JOIN pg_rewrite r   ON r.oid = d.objid
          JOIN pg_class   c   ON c.oid = r.ev_class AND c.relkind = 'v'
          JOIN pg_namespace n ON n.oid = c.relnamespace
          JOIN pg_attribute a ON a.attrelid = d.refobjid AND a.attnum = d.refobjsubid
         WHERE d.refobjid = '{SCHEMA}.{TABLE}'::regclass
           AND a.attname  = :col
    """
    rows: List[Row[Tuple[str, str, str]]] = conn.execute(text(sql), {"col": COL}).all()
    return [(r.schema_name, r.view_name, r.definition) for r in rows]


def _rewrite_text_funcs(defn: str) -> str:
    """
    通用重写：将文本函数/分支统一 cast 到 text，避免 left(jsonb,int)/CASE 混型问题
    """
    s = defn
    # "left"(e.message, 1) / left(e.message, 1) → left((e.message)::text, 1)
    s = re.sub(r'(?is)\b"left"\s*\(\s*e\.message\s*,', 'left((e.message)::text,', s)
    s = re.sub(r'(?is)\bleft\s*\(\s*e\.message\s*,', 'left((e.message)::text,', s)
    s = re.sub(r'(?is)\bleft\s*\(\s*e\.message\s*::\s*\w+\s*,', 'left((e.message)::text,', s)

    # ELSE e.message → ELSE (e.message)::text
    s = re.sub(r'(?is)\bELSE\s+e\.message\b', 'ELSE (e.message)::text', s)

    # e.message::jsonb 保持或简化成 e.message（列已为 jsonb）
    s = re.sub(r'(?i)e\.message::jsonb', 'e.message', s)
    return s


def _json_view_sql(schema: str, view: str) -> str | None:
    """
    为已知视图给 JSONB 版定义（无需猜测原始 SQL）。
    你也可以只对 v_scan_trace 定义，v_scan_recent 用默认重写。
    """
    if view == "v_scan_trace":
        # scan_ref 统一用 JSONB → text，若不是 JSON 则回退到文本
        return f"""
        CREATE VIEW {_q(schema)}.{_q(view)} AS
        SELECT
          e.id          AS event_id,
          e.source,
          e.occurred_at,
          e.message     AS message_raw,
          CASE
            WHEN e.message IS NOT NULL AND left((e.message)::text, 1) = '{{'
              THEN e.message->>'ref'
            ELSE (e.message)::text
          END           AS scan_ref,
          l.id          AS ledger_id,
          l.reason,
          l.item_id,
          /* 若你之前在视图里加入了 location_id 映射，这里可 LEFT JOIN stocks 再提取 */
          NULL::integer AS location_id,
          l.delta
        FROM {_q(SCHEMA)}.{_q("event_log")} e
        LEFT JOIN {_q(SCHEMA)}.{_q("stock_ledger")} l
          ON l.ref::text = CASE
                             WHEN e.message IS NOT NULL AND left((e.message)::text, 1) = '{{'
                               THEN e.message->>'ref'
                             ELSE (e.message)::text
                           END
        WHERE e.source LIKE 'scan_%';
        """
    if view == "v_scan_recent":
        # 你仓库若有该视图，给出一个 JSONB 兼容示例（若定义不同，请按实际改）：
        return f"""
        CREATE VIEW {_q(schema)}.{_q(view)} AS
        SELECT
          e.id          AS event_id,
          e.source,
          e.occurred_at,
          e.message     AS message_raw,
          CASE
            WHEN e.message IS NOT NULL AND left((e.message)::text, 1) = '{{'
              THEN e.message->>'ref'
            ELSE (e.message)::text
          END           AS scan_ref
        FROM {_q(SCHEMA)}.{_q("event_log")} e
        WHERE e.source LIKE 'scan_%'
        ORDER BY e.occurred_at DESC
        LIMIT 500;
        """
    return None


def upgrade() -> None:
    bind: Connection = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    # 0) 建一个 JSONB 兼容 shim：当 legacy 视图里用了 left(e.message, N) 时可继续工作
    op.execute(text("""
        CREATE OR REPLACE FUNCTION public.left(jsonb, integer)
        RETURNS text
        LANGUAGE sql
        IMMUTABLE
        STRICT
        AS $$ SELECT left(($1)::text, $2) $$;
    """))

    # 1) 捕获并删除所有依赖视图
    deps = _dep_views(bind)
    for schema, view, _ in deps:
        op.execute(text(f"DROP VIEW IF EXISTS {_q(schema)}.{_q(view)}"))

    # 2) 列类型 TEXT -> JSONB，CASE 分支统一返回 jsonb
    op.execute(text(f"""
        ALTER TABLE {_q(SCHEMA)}.{_q(TABLE)}
        ALTER COLUMN {_q(COL)} TYPE jsonb
        USING
        CASE
          WHEN pg_typeof({_q(COL)}) = 'jsonb'::regtype THEN {_q(COL)}::jsonb
          WHEN pg_typeof({_q(COL)}) = 'json'::regtype  THEN {_q(COL)}::jsonb
          ELSE to_jsonb({_q(COL)}::text)
        END
    """))

    # 3) 重建依赖视图：已知视图用 JSONB 版定义；其它按通用重写
    for schema, view, definition in deps:
        view_sql = _json_view_sql(schema, view)
        if view_sql:
            op.execute(text(view_sql))
        else:
            safe_def = _rewrite_text_funcs(definition or "")
            op.execute(text(f"CREATE VIEW {_q(schema)}.{_q(view)} AS {safe_def}"))


def downgrade() -> None:
    bind: Connection = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    deps = _dep_views(bind)
    for schema, view, _ in deps:
        op.execute(text(f"DROP VIEW IF EXISTS {_q(schema)}.{_q(view)}"))

    op.execute(text(f"""
        ALTER TABLE {_q(SCHEMA)}.{_q(TABLE)}
        ALTER COLUMN {_q(COL)} TYPE text
        USING {_q(COL)}::text
    """))

    # 删除 shim
    op.execute(text("DROP FUNCTION IF EXISTS public.left(jsonb, integer)"))

    # 按之前的定义重建（此处直接用原 definition）
    for schema, view, definition in deps:
        op.execute(text(f"CREATE VIEW {_q(schema)}.{_q(view)} AS {definition}"))
