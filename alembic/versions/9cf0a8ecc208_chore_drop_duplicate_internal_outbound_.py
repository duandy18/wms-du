"""chore: drop duplicate internal_outbound_lines foreign keys

Revision ID: 9cf0a8ecc208
Revises: 3550f648e5d7
Create Date: 2026-03-01 18:09:33.851807

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9cf0a8ecc208"
down_revision: Union[str, Sequence[str], None] = "3550f648e5d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Keep (canonical, explicitly named):
      - fk_internal_outbound_lines_doc_id   (ON DELETE CASCADE)
      - fk_internal_outbound_lines_item_id  (ON DELETE RESTRICT)

    Drop (legacy duplicates, auto-named):
      - internal_outbound_lines_doc_id_fkey
      - internal_outbound_lines_item_id_fkey
    """
    op.drop_constraint(
        "internal_outbound_lines_doc_id_fkey",
        "internal_outbound_lines",
        type_="foreignkey",
    )
    op.drop_constraint(
        "internal_outbound_lines_item_id_fkey",
        "internal_outbound_lines",
        type_="foreignkey",
    )


def downgrade() -> None:
    """Downgrade schema.

    Re-create the dropped legacy auto-named FKs (default behaviors).
    """
    op.create_foreign_key(
        "internal_outbound_lines_doc_id_fkey",
        "internal_outbound_lines",
        "internal_outbound_docs",
        ["doc_id"],
        ["id"],
    )
    op.create_foreign_key(
        "internal_outbound_lines_item_id_fkey",
        "internal_outbound_lines",
        "items",
        ["item_id"],
        ["id"],
    )
