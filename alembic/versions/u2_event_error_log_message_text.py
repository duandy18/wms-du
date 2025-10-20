# alembic/versions/u2_event_error_log_message_text.py
from alembic import op
import sqlalchemy as sa

revision = "u2_event_error_log_message_text"
down_revision = "u1_outbound_commits_unique"
def upgrade():
    op.alter_column("event_error_log", "message", type_=sa.Text())
def downgrade():
    op.alter_column("event_error_log", "message", type_=sa.String(length=255))
