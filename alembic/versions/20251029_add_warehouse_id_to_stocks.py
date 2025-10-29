# alembic/versions/20251029_add_warehouse_id_to_stocks.py
from alembic import op
import sqlalchemy as sa  # noqa

revision = "20251029_add_warehouse_id_to_stocks"
down_revision = "63af7f94ad50"
branch_labels = None
depends_on = None

def upgrade():
    # NO-OP: superseded by lockA_finalize_schema
    pass

def downgrade():
    # NO-OP
    pass
