"""Enable multi-role RBAC:
- Add unique index on user_roles(user_id, role_id)
- Sync existing primary_role_id into user_roles (once)
"""

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "2714e7999825"
down_revision = "957062093b7d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1) 添加唯一约束（避免重复角色）
    op.create_unique_constraint(
        "uq_user_roles_user_id_role_id",
        "user_roles",
        ["user_id", "role_id"],
    )

    # 2) 同步 primary_role_id → user_roles
    # 幂等：ON CONFLICT DO NOTHING
    conn.execute(
        text(
            """
            INSERT INTO user_roles (user_id, role_id)
            SELECT id AS user_id, primary_role_id AS role_id
            FROM users
            WHERE primary_role_id IS NOT NULL
            ON CONFLICT DO NOTHING
            """
        )
    )


def downgrade() -> None:
    # 不删除同步数据，只移除约束
    op.drop_constraint(
        "uq_user_roles_user_id_role_id",
        "user_roles",
        type_="unique",
    )
