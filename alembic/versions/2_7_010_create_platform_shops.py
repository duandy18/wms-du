"""create platform_shops (Phase 2.7)"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import Connection

# 根据你仓库的实际链路填写
revision = "2_7_010_create_platform_shops"
down_revision = None  # ← 若你的链路需要，改成上一版的 revision id
branch_labels = None
depends_on = None

def _is_sqlite(conn: Connection) -> bool:
    return conn.dialect.name == "sqlite"

def upgrade():
    bind = op.get_bind()
    sqlite = _is_sqlite(bind)

    op.create_table(
        "platform_shops",
        sa.Column("id", sa.Integer if sqlite else sa.BigInteger, primary_key=True),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("shop_id", sa.String(64), nullable=False),
        sa.Column("access_token", sa.Text),
        sa.Column("refresh_token", sa.Text),
        sa.Column("token_expires_at", sa.TIMESTAMP(timezone=not sqlite)),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("rate_limit_qps", sa.Integer, server_default="5"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=not sqlite), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP" if sqlite else "now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=not sqlite), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP" if sqlite else "now()")),
        sa.UniqueConstraint("platform", "shop_id", name="uq_platform_shops_platform_shop"),
    )
    op.create_index("ix_platform_shops_status", "platform_shops", ["status"])

def downgrade():
    op.drop_index("ix_platform_shops_status", table_name="platform_shops")
    op.drop_table("platform_shops")
