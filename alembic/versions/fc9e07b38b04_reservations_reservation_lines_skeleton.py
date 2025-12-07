"""reservations + reservation_lines (skeleton, idempotent + normalize existing)

Revision ID: fc9e07b38b04
Revises: 2082f8e1dad3
Create Date: 2025-11-07 18:40:28.415110
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "fc9e07b38b04"
down_revision: Union[str, Sequence[str], None] = "2082f8e1dad3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

IDX_RES_REF = "ix_reservations_ref"
IDX_RES_SHOP_REF = "ix_reservations_shop_ref"
IDX_RESLINE_RES_REFLINE = "ix_reservation_lines_res_refline"


def _has_table(bind, table: str) -> bool:
    insp = sa.inspect(bind)
    return insp.has_table(table, schema="public")


def _has_index(bind, table: str, index_name: str) -> bool:
    insp = sa.inspect(bind)
    for ix in insp.get_indexes(table, schema="public"):
        if ix.get("name") == index_name:
            return True
    return False


def _has_column(bind, table: str, col: str) -> bool:
    row = bind.execute(
        sa.text("""
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name=:t AND column_name=:c
            LIMIT 1
        """),
        {"t": table, "c": col},
    ).first()
    return row is not None


def upgrade() -> None:
    bind = op.get_bind()

    # ---- reservations ----
    if not _has_table(bind, "reservations"):
        op.create_table(
            "reservations",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("platform", sa.String(32), nullable=False),
            sa.Column("shop_id", sa.String(128), nullable=False),
            sa.Column("ref", sa.String(256), nullable=False),
            sa.Column("warehouse_id", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'PLANNED'")),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
        )
    else:
        # Normalize existing schema: add missing columns, backfill, then enforce NOT NULL/defaults
        # Add columns if missing
        if not _has_column(bind, "reservations", "platform"):
            bind.execute(sa.text("ALTER TABLE reservations ADD COLUMN platform VARCHAR(32)"))
            bind.execute(
                sa.text("UPDATE reservations SET platform = 'LEGACY' WHERE platform IS NULL")
            )
            bind.execute(sa.text("ALTER TABLE reservations ALTER COLUMN platform SET NOT NULL"))
        if not _has_column(bind, "reservations", "shop_id"):
            bind.execute(sa.text("ALTER TABLE reservations ADD COLUMN shop_id VARCHAR(128)"))
            bind.execute(
                sa.text("UPDATE reservations SET shop_id = 'NO-STORE' WHERE shop_id IS NULL")
            )
            bind.execute(sa.text("ALTER TABLE reservations ALTER COLUMN shop_id SET NOT NULL"))
        if not _has_column(bind, "reservations", "ref"):
            bind.execute(sa.text("ALTER TABLE reservations ADD COLUMN ref VARCHAR(256)"))
            bind.execute(
                sa.text("UPDATE reservations SET ref = COALESCE(ref, 'LEGACY-'||id::text)")
            )
            bind.execute(sa.text("ALTER TABLE reservations ALTER COLUMN ref SET NOT NULL"))
        if not _has_column(bind, "reservations", "warehouse_id"):
            bind.execute(sa.text("ALTER TABLE reservations ADD COLUMN warehouse_id INTEGER"))
            bind.execute(
                sa.text("UPDATE reservations SET warehouse_id = 0 WHERE warehouse_id IS NULL")
            )
            bind.execute(sa.text("ALTER TABLE reservations ALTER COLUMN warehouse_id SET NOT NULL"))
        if not _has_column(bind, "reservations", "status"):
            bind.execute(sa.text("ALTER TABLE reservations ADD COLUMN status VARCHAR(16)"))
            bind.execute(sa.text("UPDATE reservations SET status = 'PLANNED' WHERE status IS NULL"))
            bind.execute(sa.text("ALTER TABLE reservations ALTER COLUMN status SET NOT NULL"))
            bind.execute(
                sa.text("ALTER TABLE reservations ALTER COLUMN status SET DEFAULT 'PLANNED'")
            )
        if not _has_column(bind, "reservations", "created_at"):
            bind.execute(sa.text("ALTER TABLE reservations ADD COLUMN created_at TIMESTAMPTZ"))
            bind.execute(
                sa.text("UPDATE reservations SET created_at = now() WHERE created_at IS NULL")
            )
            bind.execute(sa.text("ALTER TABLE reservations ALTER COLUMN created_at SET NOT NULL"))
            bind.execute(
                sa.text("ALTER TABLE reservations ALTER COLUMN created_at SET DEFAULT now()")
            )

    # Indexes (create only if columns exist and index not present)
    if _has_column(bind, "reservations", "ref") and not _has_index(
        bind, "reservations", IDX_RES_REF
    ):
        op.create_index(IDX_RES_REF, "reservations", ["ref"])
    if all(
        _has_column(bind, "reservations", c) for c in ("platform", "shop_id", "ref")
    ) and not _has_index(bind, "reservations", IDX_RES_SHOP_REF):
        op.create_index(
            IDX_RES_SHOP_REF, "reservations", ["platform", "shop_id", "ref"], unique=False
        )

    # ---- reservation_lines ----
    if not _has_table(bind, "reservation_lines"):
        op.create_table(
            "reservation_lines",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column(
                "reservation_id",
                sa.BigInteger(),
                sa.ForeignKey("reservations.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("ref_line", sa.Integer(), nullable=False),
            sa.Column("item_id", sa.Integer(), nullable=False),
            sa.Column("qty", sa.Integer(), nullable=False),
            sa.Column("batch_id", sa.BigInteger(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
        )

    if all(
        _has_column(bind, "reservation_lines", c) for c in ("reservation_id", "ref_line")
    ) and not _has_index(bind, "reservation_lines", IDX_RESLINE_RES_REFLINE):
        op.create_index(
            IDX_RESLINE_RES_REFLINE,
            "reservation_lines",
            ["reservation_id", "ref_line"],
            unique=True,
        )


def downgrade() -> None:
    bind = op.get_bind()

    # Drop in reverse order, if present
    if _has_index(bind, "reservation_lines", IDX_RESLINE_RES_REFLINE):
        op.drop_index(INDEX_NAME=IDX_RESLINE_RES_REFLINE, table_name="reservation_lines")
    if _has_table(bind, "reservation_lines"):
        op.drop_table("reservation_lines")

    if _has_index(bind, "reservations", IDX_RES_SHOP_REF):
        op.drop_index(INDEX_NAME=IDX_RES_SHOP_REF, table_name="reservations")
    if _has_index(bind, "reservations", IDX_RES_REF):
        op.drop_index(INDEX_NAME=IDX_RES_REF, table_name="reservations")
    if _has_table(bind, "reservations"):
        op.drop_table("reservations")
