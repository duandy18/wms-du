# alembic/versions/2_7_0001_sqlite_event_error_log.py
from alembic import op
import sqlalchemy as sa

revision = "2_7_0001_sqlite"
down_revision = "<上一版本>"

def upgrade():
    op.create_table(
        "event_error_log",
        sa.Column("id", sa.Integer, primary_key=True),  # SQLite 无 BigSerial
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("shop_id", sa.String(64), nullable=False),
        sa.Column("order_no", sa.String(128), nullable=False),
        sa.Column("idempotency_key", sa.String(256), nullable=False),
        sa.Column("from_state", sa.String(32)),
        sa.Column("to_state", sa.String(32), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=False),
        sa.Column("error_msg", sa.Text),
        sa.Column("payload_json", sa.Text),   # JSONB → TEXT
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("max_retries", sa.Integer, nullable=False, server_default="5"),
        sa.Column("next_retry_at", sa.TIMESTAMP()),      # 无 tz
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False, server_default=sa.text("(datetime('now'))")),
        sa.Column("updated_at", sa.TIMESTAMP(), nullable=False, server_default=sa.text("(datetime('now'))")),
    )
    op.create_index("ix_event_error_log_key", "event_error_log", ["platform","shop_id","idempotency_key"])

def downgrade():
    op.drop_index("ix_event_error_log_key", table_name="event_error_log")
    op.drop_table("event_error_log")
