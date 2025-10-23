"""event_error_log.message -> TEXT (idempotent)

Revision ID: u2_event_error_log_message_text
Revises: u1_outbound_commits_unique
Create Date: 2025-10-XX
"""
from __future__ import annotations

from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "u2_event_error_log_message_text"
down_revision: str | Sequence[str] | None = "u1_outbound_commits_unique"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    dname = (bind.dialect.name or "").lower()
    if dname == "sqlite":
        # SQLite: pragma table_info
        rows = bind.exec_driver_sql(f"PRAGMA table_info({table})").all()
        cols = {r[1] for r in rows}  # (cid, name, type, notnull, dflt_value, pk)
        return column in cols
    # PostgreSQL & others: information_schema
    row = bind.execute(
        text(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_name=:t AND column_name=:c
            """
        ),
        {"t": table, "c": column},
    ).first()
    return bool(row)


def upgrade() -> None:
    """
    老版本库存在 event_error_log.message（VARCHAR/NVARCHAR），需要扩到 TEXT。
    新版本库已经用 error_msg，不再有 message —— 在这种情况下 NO-OP。
    """
    if _has_column("event_error_log", "message"):
        op.alter_column("event_error_log", "message", type_=sa.Text())
    else:
        # 新库只有 error_msg；无需任何动作
        pass


def downgrade() -> None:
    """
    降级保持幂等：若存在 message 列则改回较短类型，否则 NO-OP。
    注意：具体长度在不同历史版本中不一致，这里用 VARCHAR(255) 作为最保守回退。
    """
    if _has_column("event_error_log", "message"):
        op.alter_column("event_error_log", "message", type_=sa.String(length=255))
