"""events core tables: platform_events, event_log, event_error_log, event_replay_cursor

Revision ID: 20251030_events_core_tables
Revises: 20251030_channel_inventory_add_visible
Create Date: 2025-10-30
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# ---- Alembic identifiers ----
revision = "20251030_events_core_tables"
down_revision = "20251030_channel_inventory_add_visible"
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

def _has_unique(table: str, name: str) -> bool:
    try:
        return any(uc["name"] == name for uc in _insp().get_unique_constraints(table))
    except Exception:
        return False

def _has_column(table: str, column: str) -> bool:
    try:
        return any(col["name"] == column for col in _insp().get_columns(table))
    except Exception:
        return False


def upgrade():
    # ---------------- 1) platform_events ----------------
    if not _has_table("platform_events"):
        op.create_table(
            "platform_events",
            sa.Column("id", sa.BigInteger, primary_key=True),
            sa.Column("platform", sa.Text, nullable=False),
            sa.Column("event_type", sa.Text, nullable=False),
            sa.Column("event_id", sa.Text, nullable=False),
            sa.Column("occurred_at", sa.TIMESTAMP(timezone=True), nullable=False),
            sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("status", sa.Text, nullable=False, server_default=sa.text("'NEW'")),
            sa.Column(
                "dedup_key",
                sa.Text,
                sa.Computed("(platform || ':' || event_type || ':' || event_id)", persisted=True),
                nullable=False,
            ),
            sa.CheckConstraint(
                "status in ('NEW','NORMALIZED','DISPATCHED','PERSISTED','ERROR')",
                name="ck_platform_events_status",
            ),
        )
    if not _has_index("platform_events", "ix_platform_events_platform_occurred"):
        op.create_index(
            "ix_platform_events_platform_occurred",
            "platform_events",
            ["platform", "occurred_at"],
            unique=False,
        )
    if not _has_unique("platform_events", "uq_platform_events_dedup"):
        op.create_unique_constraint("uq_platform_events_dedup", "platform_events", ["dedup_key"])

    # ---------------- 2) event_log ----------------
    if not _has_table("event_log"):
        op.create_table(
            "event_log",
            sa.Column("id", sa.BigInteger, primary_key=True),
            sa.Column("source", sa.Text, nullable=False),  # ingest|normalize|dispatch|persist|gateway|adapter...
            sa.Column("level", sa.Text, nullable=False, server_default=sa.text("'INFO'")),
            sa.Column("message", sa.Text, nullable=False),
            sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb")),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.CheckConstraint("level in ('DEBUG','INFO','WARN','ERROR')", name="ck_event_log_level"),
        )
    if not _has_index("event_log", "ix_event_log_created_at"):
        op.create_index("ix_event_log_created_at", "event_log", ["created_at"], unique=False)
    if not _has_index("event_log", "ix_event_log_level"):
        op.create_index("ix_event_log_level", "event_log", ["level"], unique=False)

    # ---------------- 3) event_error_log ----------------
    if not _has_table("event_error_log"):
        op.create_table(
            "event_error_log",
            sa.Column("id", sa.BigInteger, primary_key=True),
            sa.Column("dedup_key", sa.Text, nullable=False),
            sa.Column("stage", sa.Text, nullable=False),  # ingest|normalize|dispatch|persist
            sa.Column("error", sa.Text, nullable=False),
            sa.Column("occurred_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.CheckConstraint("stage in ('ingest','normalize','dispatch','persist')", name="ck_event_error_stage"),
        )
    else:
        # 历史表：逐列补齐
        if not _has_column("event_error_log", "dedup_key"):
            op.add_column("event_error_log", sa.Column("dedup_key", sa.Text, nullable=False, server_default=sa.text("''")))
            # 去掉默认以允许后续正常插入
            op.alter_column("event_error_log", "dedup_key", server_default=None)
        if not _has_column("event_error_log", "stage"):
            op.add_column("event_error_log", sa.Column("stage", sa.Text, nullable=False, server_default=sa.text("'ingest'")))
            op.alter_column("event_error_log", "stage", server_default=None)
        if not _has_column("event_error_log", "error"):
            op.add_column("event_error_log", sa.Column("error", sa.Text, nullable=False, server_default=sa.text("''")))
            op.alter_column("event_error_log", "error", server_default=None)
        if not _has_column("event_error_log", "occurred_at"):
            op.add_column(
                "event_error_log",
                sa.Column("occurred_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
            )
            # 通常可保留默认；若你不想默认，可在后续独立迁移取消

        # 历史表缺少 CHECK 约束时不强行补（不同 PG 版本命名复杂）；必要时另起小迁移加 ck。

    # 索引兜底（此时相关列已存在）
    if not _has_index("event_error_log", "ix_event_error_occurred"):
        op.create_index("ix_event_error_occurred", "event_error_log", ["occurred_at"], unique=False)
    if not _has_index("event_error_log", "ix_event_error_stage"):
        op.create_index("ix_event_error_stage", "event_error_log", ["stage"], unique=False)

    # ---------------- 4) event_replay_cursor ----------------
    if not _has_table("event_replay_cursor"):
        op.create_table(
            "event_replay_cursor",
            sa.Column("id", sa.BigInteger, primary_key=True),
            sa.Column("platform", sa.Text, nullable=False, unique=True),
            sa.Column(
                "last_event_ts",
                sa.TIMESTAMP(timezone=True),
                nullable=False,
                server_default=sa.text("'1970-01-01 00:00:00+00'"),
            ),
        )
    if not _has_index("event_replay_cursor", "ix_event_replay_cursor_platform"):
        op.create_index("ix_event_replay_cursor_platform", "event_replay_cursor", ["platform"], unique=False)


def downgrade():
    # 注意：若线上已有数据，回滚会删表，请谨慎执行。
    if _has_index("event_replay_cursor", "ix_event_replay_cursor_platform"):
        op.drop_index("ix_event_replay_cursor_platform", table_name="event_replay_cursor")
    if _has_table("event_replay_cursor"):
        op.drop_table("event_replay_cursor")

    if _has_index("event_error_log", "ix_event_error_stage"):
        op.drop_index("ix_event_error_stage", table_name="event_error_log")
    if _has_index("event_error_log", "ix_event_error_occurred"):
        op.drop_index("ix_event_error_occurred", table_name="event_error_log")
    if _has_table("event_error_log"):
        op.drop_table("event_error_log")

    if _has_index("event_log", "ix_event_log_level"):
        op.drop_index("ix_event_log_level", table_name="event_log")
    if _has_index("event_log", "ix_event_log_created_at"):
        op.drop_index("ix_event_log_created_at", table_name="event_log")
    if _has_table("event_log"):
        op.drop_table("event_log")

    if _has_unique("platform_events", "uq_platform_events_dedup"):
        op.drop_constraint("uq_platform_events_dedup", "platform_events", type_="unique")
    if _has_index("platform_events", "ix_platform_events_platform_occurred"):
        op.drop_index("ix_platform_events_platform_occurred", table_name="platform_events")
    if _has_table("platform_events"):
        op.drop_table("platform_events")
