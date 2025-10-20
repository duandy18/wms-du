"""add event_error_log table"""

from alembic import op
import sqlalchemy as sa

# 注意：revision 保持短一些，避免 32 长度问题
revision = "e1e0g01"
down_revision = "20251016_add_outbound_commits"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "event_error_log",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("event_id", sa.String(length=64), nullable=True),
        sa.Column("error_type", sa.String(length=64), nullable=False),
        sa.Column("message", sa.String(length=255), nullable=True),
        sa.Column("payload", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )


def downgrade():
    op.drop_table("event_error_log")
