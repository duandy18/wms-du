from alembic import op
import sqlalchemy as sa

revision = "u3_outbound_commits_shop_id"
down_revision = "u2_event_error_log_message_text"  # 按你的链条调整
branch_labels = None
depends_on = None

def upgrade():
    # 补列
    op.add_column("outbound_commits", sa.Column("shop_id", sa.String(length=64), nullable=False, server_default=""))
    # 老索引若存在可移除
    try:
        op.drop_index("ux_outbound_commits_3cols", table_name="outbound_commits")
    except Exception:
        pass
    # 新唯一索引（平台 × 店铺 × 单号 × 状态）
    op.create_index(
        "ux_outbound_commits_4cols",
        "outbound_commits",
        ["platform", "shop_id", "ref", "state"],
        unique=True,
    )

def downgrade():
    try:
        op.drop_index("ux_outbound_commits_4cols", table_name="outbound_commits")
    except Exception:
        pass
    op.drop_column("outbound_commits", "shop_id")
