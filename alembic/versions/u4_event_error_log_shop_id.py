from alembic import op
import sqlalchemy as sa

revision = "u4_event_error_log_shop_id"
down_revision = "u3_outbound_commits_shop_id"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("event_error_log", sa.Column("shop_id", sa.String(length=64), nullable=True))

def downgrade():
    op.drop_column("event_error_log", "shop_id")
