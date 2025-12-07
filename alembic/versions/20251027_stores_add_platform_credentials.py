"""stores: add platform credentials (app_key/app_secret/callback_url)

Revision ID: 20251027_stores_add_platform_credentials
Revises: 20251026_outbound_ship_ops
Create Date: 2025-10-27 09:00:00
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251027_stores_add_platform_credentials"
down_revision = "20251026_outbound_ship_ops"  # 若你当前 head 不同，请改成实际 head
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("stores") as b:
        b.add_column(sa.Column("app_key", sa.String(length=128), nullable=True))
        b.add_column(sa.Column("app_secret", sa.String(length=256), nullable=True))
        b.add_column(sa.Column("callback_url", sa.String(length=256), nullable=True))


def downgrade():
    with op.batch_alter_table("stores") as b:
        b.drop_column("callback_url")
        b.drop_column("app_secret")
        b.drop_column("app_key")
