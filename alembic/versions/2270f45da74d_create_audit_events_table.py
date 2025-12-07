"""create audit_events table (idempotent if table pre-exists)

Revision ID: 2270f45da74d
Revises: d8a8390470c7
Create Date: 2025-11-07 12:42:28.654975
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "2270f45da74d"
down_revision: Union[str, Sequence[str], None] = "d8a8390470c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TBL = "audit_events"


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 1) 若表不存在则创建（如果你已经手工建了，就会跳过）
    if not insp.has_table(_TBL):
        op.create_table(
            _TBL,
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("category", sa.String(length=64), nullable=False),
            sa.Column("ref", sa.String(length=128), nullable=False),
            sa.Column("meta", sa.dialects.postgresql.JSONB, nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
        )

    # 2) 索引：用 IF NOT EXISTS 防重复
    bind.execute(
        sa.text(f"CREATE INDEX IF NOT EXISTS ix_audit_events_category ON {_TBL} (category)")
    )
    bind.execute(sa.text(f"CREATE INDEX IF NOT EXISTS ix_audit_events_ref ON {_TBL} (ref)"))


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DROP INDEX IF EXISTS ix_audit_events_ref"))
    bind.execute(sa.text("DROP INDEX IF EXISTS ix_audit_events_category"))
    bind.execute(sa.text(f"DROP TABLE IF EXISTS {_TBL}"))
