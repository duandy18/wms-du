"""phase_m2 lots shelf_life checks use expiry_policy_snapshot

Revision ID: 1c0ba6683ef7
Revises: cb1f781f78bf
Create Date: 2026-02-28 16:43:59.236720

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1c0ba6683ef7"
down_revision: Union[str, Sequence[str], None] = "cb1f781f78bf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_NEW_CK = "ck_lots_sl_params_by_policy_snap"
_OLD_CK = "ck_lots_item_shelf_life_params_only_when_enabled_snapshot"


def upgrade() -> None:
    """
    lots：将 shelf_life 参数约束从 legacy 镜像字段迁移到真相字段

    旧：
      ck_lots_item_shelf_life_params_only_when_enabled_snapshot
        依赖 item_has_shelf_life_snapshot

    新：
      ck_lots_sl_params_by_policy_snap
        依赖 item_expiry_policy_snapshot
        规则：当 policy != REQUIRED 时，shelf_life_value/unit 必须都为 NULL
    """
    op.drop_constraint(_OLD_CK, "lots", type_="check")

    op.create_check_constraint(
        _NEW_CK,
        "lots",
        "(item_expiry_policy_snapshot = 'REQUIRED'::expiry_policy OR "
        "(item_shelf_life_value_snapshot IS NULL AND item_shelf_life_unit_snapshot IS NULL))",
    )


def downgrade() -> None:
    op.drop_constraint(_NEW_CK, "lots", type_="check")

    op.create_check_constraint(
        _OLD_CK,
        "lots",
        "("
        "item_has_shelf_life_snapshot IS NULL OR "
        "item_has_shelf_life_snapshot = true OR "
        "(item_shelf_life_value_snapshot IS NULL AND item_shelf_life_unit_snapshot IS NULL)"
        ")",
    )
