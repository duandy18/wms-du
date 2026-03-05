"""feat(pricing): add check constraint for scheme ruleset_key

Revision ID: a8235d7af4f7
Revises: 1c236105fb46
Create Date: 2026-01-27 18:23:04.470336

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a8235d7af4f7"
down_revision: Union[str, Sequence[str], None] = "1c236105fb46"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_CONSTRAINT_NAME = "ck_shipping_provider_pricing_schemes_ruleset_key"


def upgrade() -> None:
    """
    RS0：scheme.ruleset_key 的有限集合约束（DB 级事实）

    允许值：
    - segments_standard
    - first_next_1kg
    - first_next_5kg_remote
    """
    op.create_check_constraint(
        _CONSTRAINT_NAME,
        "shipping_provider_pricing_schemes",
        "ruleset_key IN ("
        "'segments_standard',"
        "'first_next_1kg',"
        "'first_next_5kg_remote'"
        ")",
    )


def downgrade() -> None:
    op.drop_constraint(
        _CONSTRAINT_NAME,
        "shipping_provider_pricing_schemes",
        type_="check",
    )
