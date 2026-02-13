"""chore: add comment for pick_tasks.scope

Revision ID: bc49a23d6ed0
Revises: 65b26d28aa8f
Create Date: 2026-02-13 15:32:55.282179
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "bc49a23d6ed0"
down_revision: Union[str, Sequence[str], None] = "65b26d28aa8f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_COMMENT = "作业 scope（PROD/DRILL）。DRILL 与 PROD 作业宇宙隔离。"


def upgrade() -> None:
    op.execute(
        f"COMMENT ON COLUMN public.pick_tasks.scope IS '{_COMMENT}'"
    )


def downgrade() -> None:
    op.execute(
        "COMMENT ON COLUMN public.pick_tasks.scope IS NULL"
    )
