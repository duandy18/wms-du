"""chore(items): sync case_* column comments

Revision ID: b93448767675
Revises: ac946e8572a4
Create Date: 2026-02-21 11:46:28.059374

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "b93448767675"
down_revision: Union[str, Sequence[str], None] = "ac946e8572a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_CASE_RATIO_COMMENT = "箱装换算倍率（整数）；1 case_uom = case_ratio × uom（最小单位）；允许为空（未治理）"
_CASE_UOM_COMMENT = "箱装单位名（展示/输入偏好），如“箱”；允许为空（未治理）"


def upgrade() -> None:
    op.alter_column("items", "case_ratio", comment=_CASE_RATIO_COMMENT)
    op.alter_column("items", "case_uom", comment=_CASE_UOM_COMMENT)


def downgrade() -> None:
    op.alter_column("items", "case_ratio", comment=None)
    op.alter_column("items", "case_uom", comment=None)
