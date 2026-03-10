"""drop group name unique constraint

Revision ID: 33c405a7eecd
Revises: 433ded5e6f93
Create Date: 2026-03-09 18:57:01.473912

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "33c405a7eecd"
down_revision: Union[str, Sequence[str], None] = "433ded5e6f93"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Remove legacy uniqueness constraint on (module_id, name).

    After groups CRUD refactor:
    - group identity = group_id
    - name becomes display-only label
    """

    op.drop_constraint(
        "uq_sp_dest_groups_module_name",
        "shipping_provider_destination_groups",
        type_="unique",
    )


def downgrade() -> None:
    """
    Restore legacy constraint (for rollback).
    """

    op.create_unique_constraint(
        "uq_sp_dest_groups_module_name",
        "shipping_provider_destination_groups",
        ["module_id", "name"],
    )
