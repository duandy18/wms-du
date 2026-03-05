"""phase_m2 add item_uoms packaging table

Revision ID: 3294e8be11b1
Revises: 9e7f145c0bfd
Create Date: 2026-02-28 15:24:21.580541

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "3294e8be11b1"
down_revision: Union[str, Sequence[str], None] = "9e7f145c0bfd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    item_uoms（多包装结构化，Phase M-2）：

    - create table item_uoms
    - unique(item_id, uom)
    - partial unique: one base per item (item_id WHERE is_base = true)
    - check ratio_to_base >= 1
    - backfill:
      - base row: (item_id, items.uom, ratio=1, is_base=true, defaults=true)
      - case row: (item_id, items.case_uom, ratio=items.case_ratio) when both not null
    """
    op.create_table(
        "item_uoms",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("uom", sa.String(length=16), nullable=False),
        sa.Column("ratio_to_base", sa.Integer(), nullable=False),
        sa.Column("display_name", sa.String(length=32), nullable=True),
        sa.Column("is_base", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_purchase_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_inbound_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_outbound_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="RESTRICT"),
    )

    # unique(item_id, uom)
    op.create_unique_constraint(
        "uq_item_uoms_item_uom",
        "item_uoms",
        ["item_id", "uom"],
    )

    # one base per item (partial unique index)
    op.create_index(
        "uq_item_uoms_one_base_per_item",
        "item_uoms",
        ["item_id"],
        unique=True,
        postgresql_where=sa.text("is_base = true"),
    )

    # ratio_to_base >= 1
    op.create_check_constraint(
        "ck_item_uoms_ratio_ge_1",
        "item_uoms",
        "ratio_to_base >= 1",
    )

    # backfill base uom
    op.execute(
        """
        INSERT INTO item_uoms (
            item_id,
            uom,
            ratio_to_base,
            display_name,
            is_base,
            is_purchase_default,
            is_inbound_default,
            is_outbound_default
        )
        SELECT
            id,
            uom,
            1,
            uom,
            true,
            true,
            true,
            true
        FROM items
        """
    )

    # backfill case uom (one-layer packaging) if exists
    op.execute(
        """
        INSERT INTO item_uoms (
            item_id,
            uom,
            ratio_to_base,
            display_name,
            is_base,
            is_purchase_default,
            is_inbound_default,
            is_outbound_default
        )
        SELECT
            id,
            case_uom,
            case_ratio,
            case_uom,
            false,
            false,
            false,
            false
        FROM items
        WHERE case_ratio IS NOT NULL
          AND case_uom IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_index("uq_item_uoms_one_base_per_item", table_name="item_uoms")
    op.drop_constraint("ck_item_uoms_ratio_ge_1", "item_uoms", type_="check")
    op.drop_constraint("uq_item_uoms_item_uom", "item_uoms", type_="unique")
    op.drop_table("item_uoms")
