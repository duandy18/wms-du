# alembic/versions/20251029_lockA_add_wh_and_batch_code.py
import sqlalchemy as sa  # noqa

revision = "20251029_lockA_add_wh_and_batch_code"
down_revision = "63af7f94ad50"
branch_labels = None
depends_on = None


def upgrade():
    # NO-OP: superseded by lockA_finalize_schema
    pass


def downgrade():
    # NO-OP
    pass
