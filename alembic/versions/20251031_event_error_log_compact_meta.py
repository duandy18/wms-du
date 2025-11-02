"""compact event_error_log: move verbose columns into meta JSONB and drop them (dependency-aware)

Revision ID: 20251031_event_error_log_compact_meta
Revises: 20251030_events_core_tables
Create Date: 2025-10-31
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# ---- Alembic identifiers ----
revision = "20251031_event_error_log_compact_meta"
down_revision = "20251030_events_core_tables"
branch_labels = None
depends_on = None

# 计划保留的最小接口：dedup_key, stage, error, occurred_at, meta
# 其余列若不存在依赖则删除；若存在依赖（如视图/函数）则暂留并标注为deprecated。
EXTRA_COLS = [
    "error_code", "error_type", "error_msg", "message",
    "event_id", "order_no", "shop_id", "platform",
    "from_state", "to_state", "idempotency_key",
    "retry_count", "max_retries", "next_retry_at",
    "payload", "payload_json",
    "created_at", "updated_at",
]

def _insp():
    bind = op.get_bind()
    return sa.inspect(bind)

def _has_table(name: str) -> bool:
    return _insp().has_table(name)

def _has_column(table: str, col: str) -> bool:
    return any(c["name"] == col for c in _insp().get_columns(table))

def _existing_indexes(table: str):
    return [ix["name"] for ix in _insp().get_indexes(table)]

def _add_meta_if_absent():
    if not _has_column("event_error_log", "meta"):
        op.add_column(
            "event_error_log",
            sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        )
        op.alter_column("event_error_log", "meta", server_default=None)

def _dependent_views_for_column(table: str, column: str):
    # 查找依赖此列的视图（不含物化/函数依赖的复杂情况）
    sql = sa.text("""
        SELECT DISTINCT n.nspname || '.' || c.relname AS view_name
        FROM pg_catalog.pg_attribute a
        JOIN pg_catalog.pg_class t ON a.attrelid = t.oid
        JOIN pg_catalog.pg_depend d ON d.refobjid = t.oid AND d.refobjsubid = a.attnum
        JOIN pg_catalog.pg_rewrite r ON r.oid = d.objid
        JOIN pg_catalog.pg_class c ON c.oid = r.ev_class
        JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
        WHERE t.relkind = 'r'
          AND c.relkind = 'v'
          AND t.relname = :table
          AND a.attname = :column
    """)
    rows = _insp().bind.execute(sql, {"table": table, "column": column}).fetchall()
    return [r[0] for r in rows]

def upgrade():
    if not _has_table("event_error_log"):
        return

    _add_meta_if_absent()

    # 1) 把扩展列打包进 meta（仅对存在的列）
    pairs = []
    for c in EXTRA_COLS:
        if _has_column("event_error_log", c):
            pairs.append(f"'{c}', {sa.text(c).text}")
    if pairs:
        kv = ", ".join(pairs)
        op.execute(sa.text(
            f"""
            UPDATE event_error_log
               SET meta = COALESCE(meta, '{{}}'::jsonb) || jsonb_strip_nulls(jsonb_build_object({kv}));
            """
        ))

    # 2) 逐列尝试删除：若有依赖视图，则跳过删除并打上deprecated标注
    for c in EXTRA_COLS:
        if _has_column("event_error_log", c):
            deps = _dependent_views_for_column("event_error_log", c)
            if deps:
                # 标注为废弃，便于后续治理（COMMENT 不会影响性能）
                op.execute(sa.text(
                    f"COMMENT ON COLUMN event_error_log.{c} IS 'DEPRECATED: moved into meta; referenced by views: {', '.join(deps)}';"
                ))
            else:
                op.drop_column("event_error_log", c)

    # 3) 给 meta 建 GIN 索引（若尚未存在）
    idx_name = "ix_event_error_log_meta_gin"
    if idx_name not in _existing_indexes("event_error_log"):
        op.execute(sa.text(f"CREATE INDEX {idx_name} ON event_error_log USING gin (meta)"))

def downgrade():
    # 弱可逆：仅恢复被删的列壳，并尽力从 meta 回填
    if not _has_table("event_error_log"):
        return

    # 1) 还原列（可空）
    ts_cols = ["created_at", "updated_at", "next_retry_at"]
    text_cols = [
        "error_code", "error_type", "error_msg", "message",
        "event_id", "order_no", "shop_id", "platform",
        "from_state", "to_state", "idempotency_key",
        "payload", "payload_json",
    ]
    int_cols = ["retry_count", "max_retries"]

    for c in ts_cols:
        if not _has_column("event_error_log", c):
            op.add_column("event_error_log", sa.Column(c, sa.TIMESTAMP(timezone=True), nullable=True))
    for c in text_cols:
        if not _has_column("event_error_log", c):
            op.add_column("event_error_log", sa.Column(c, sa.Text, nullable=True))
    for c in int_cols:
        if not _has_column("event_error_log", c):
            op.add_column("event_error_log", sa.Column(c, sa.Integer, nullable=True))

    # 2) 从 meta 回填（存在键才覆盖）
    sets = []
    for k in text_cols:
        sets.append(f"""{k} = COALESCE(meta->>'{k}', {k})""")
    for k in int_cols:
        sets.append(f"""{k} = COALESCE(NULLIF(meta->>'{k}','')::int, {k})""")
    for k in ts_cols:
        sets.append(f"""{k} = COALESCE(NULLIF(meta->>'{k}','')::timestamptz, {k})""")
    if sets and _has_column("event_error_log", "meta"):
        op.execute(sa.text(f"UPDATE event_error_log SET {', '.join(sets)}"))

    # 3) 删 GIN 索引（若存在）
    op.execute(sa.text("DROP INDEX IF EXISTS ix_event_error_log_meta_gin"))
