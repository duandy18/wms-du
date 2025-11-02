"""drop legacy columns and indexes from event_error_log after meta migration

Revision ID: 20251031_event_error_log_drop_legacy_columns
Revises: 20251031_event_error_log_compact_meta
Create Date: 2025-10-31
"""
from alembic import op
import sqlalchemy as sa

revision = "20251031_event_error_log_drop_legacy_columns"
down_revision = "20251031_event_error_log_compact_meta"
branch_labels = None
depends_on = None

DROP_COLS = [
    "platform", "event_id", "error_type", "message", "payload",
    "created_at", "shop_id", "order_no", "idempotency_key",
    "from_state", "to_state", "error_code", "error_msg",
    "payload_json", "retry_count", "max_retries",
    "next_retry_at", "updated_at",
]

DROP_INDEXES = [
    # 旧键索引，引用了将要删除的列
    ("event_error_log", "ix_event_error_log_key"),
    ("event_error_log", "ix_event_error_log_retry"),
]

def _insp():
    bind = op.get_bind()
    return sa.inspect(bind)

def _has_table(name: str) -> bool:
    return _insp().has_table(name)

def _has_column(table: str, col: str) -> bool:
    return any(c["name"] == col for c in _insp().get_columns(table))

def _has_index(table: str, name: str) -> bool:
    return any(ix["name"] == name for ix in _insp().get_indexes(table))

def _dependent_views_for_column(table: str, column: str):
    sql = sa.text("""
        SELECT n.nspname || '.' || c.relname AS view_name
        FROM pg_attribute a
        JOIN pg_class t ON a.attrelid = t.oid
        JOIN pg_depend d ON d.refobjid = t.oid AND d.refobjsubid = a.attnum
        JOIN pg_rewrite r ON r.oid = d.objid
        JOIN pg_class c ON c.oid = r.ev_class
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE t.relkind = 'r' AND c.relkind IN ('v','m')
          AND t.relname = :table AND a.attname = :column
    """)
    return [row[0] for row in _insp().bind.execute(sql, {"table": table, "column": column}).fetchall()]

def upgrade():
    if not _has_table("event_error_log"):
        return

    # 1) 先删旧索引（避免列删不掉）
    for table, idx in DROP_INDEXES:
        if _has_index(table, idx):
            op.drop_index(idx, table_name=table)

    # 2) 删不再被依赖的列；仍有依赖则跳过
    for col in DROP_COLS:
        if _has_column("event_error_log", col):
            deps = _dependent_views_for_column("event_error_log", col)
            if deps:
                # 仍有对象依赖，保留并标注
                op.execute(sa.text(
                    f"COMMENT ON COLUMN event_error_log.{col} IS 'DEPRECATED: still referenced by {', '.join(deps)}';"
                ))
            else:
                op.drop_column("event_error_log", col)

def downgrade():
    # 弱可逆：只恢复关键壳列（可空），索引不恢复
    if not _has_table("event_error_log"):
        return

    restore_cols = {
        "platform": sa.Text,
        "event_id": sa.Text,
        "error_type": sa.Text,
        "message": sa.Text,
        "payload": sa.Text,         # 原可能为 json；弱可逆用 Text
        "created_at": sa.TIMESTAMP(timezone=True),
        "shop_id": sa.Text,
        "order_no": sa.Text,
        "idempotency_key": sa.Text,
        "from_state": sa.Text,
        "to_state": sa.Text,
        "error_code": sa.Text,
        "error_msg": sa.Text,
        "payload_json": sa.Text,    # 原为 jsonb；弱可逆用 Text
        "retry_count": sa.Integer,
        "max_retries": sa.Integer,
        "next_retry_at": sa.TIMESTAMP(timezone=True),
        "updated_at": sa.TIMESTAMP(timezone=True),
    }
    for col, typ in restore_cols.items():
        if not _has_column("event_error_log", col):
            op.add_column("event_error_log", sa.Column(col, typ, nullable=True))
