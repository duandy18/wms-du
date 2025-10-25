from alembic import op
import sqlalchemy as sa

revision = "20251023_event_store"
down_revision = "fe8d88377401"  # 替换为当前 head

def upgrade():
    op.create_table(
        "event_store",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("topic", sa.String(64), nullable=False),
        sa.Column("key", sa.String(128), nullable=True),  # 幂等键，如 order_id#line
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("headers", sa.JSON, nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="PENDING"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column("checksum", sa.String(64), nullable=True),
        sa.Index("ix_event_topic_status", "topic", "status"),
        sa.UniqueConstraint("topic", "key", name="uq_event_topic_key")  # 幂等
    )

def downgrade():
    op.drop_table("event_store")
