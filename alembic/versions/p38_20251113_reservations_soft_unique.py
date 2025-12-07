"""phase38: add business unique key for soft reservations

Revision ID: p38_20251113_reservations_soft_unique
Revises: p37_20251112_soft_reserve_cleanup_drop_location
Create Date: 2025-11-13 00:00:00.000000
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "p38_20251113_reservations_soft_unique"
down_revision = "p37_20251112_soft_reserve_cleanup_drop_location"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """为 soft-reserve 幂等插入补充业务唯一键。

    目标：
      - 支持 INSERT ... ON CONFLICT (platform, shop_id, warehouse_id, ref) DO NOTHING
      - 保证同一平台+店铺+仓库+业务 ref 只存在一条 reservation
    """
    op.create_unique_constraint(
        "uq_reservations_platform_shop_wh_ref",
        "reservations",
        ["platform", "shop_id", "warehouse_id", "ref"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_reservations_platform_shop_wh_ref",
        "reservations",
        type_="unique",
    )
