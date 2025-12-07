"""widen alembic_version.version_num to 255 for long revision ids

Revision ID: u0_widen_alembic_version_num
Revises: f995a82ac74e
Create Date: 2025-10-21

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "u0_widen_alembic_version_num"
down_revision = "f995a82ac74e"
branch_labels = None
depends_on = None


def upgrade():
    # Postgres: 将版本号列从 VARCHAR(32) 扩到 255，以容纳类似 '20251006_add_constraints_to_stocks' 的长 id
    op.execute("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(255);")


def downgrade():
    # 若要回退为 32，可执行以下语句；注意若表里已有长于 32 的 id 会报错
    # op.execute("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(32);")
    pass
