"""phase m4: inbound_receipt_lines allow draft null lot and lock on confirm

Revision ID: 5b4ff22a3818
Revises: a2fa02caf006
Create Date: 2026-03-01 13:40:58.857275

- add receipt_status_snapshot to lines (DRAFT/CONFIRMED)
- allow lot_id nullable for DRAFT adjustments
- enforce CONFIRMED requires lot_id (DB-level)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "5b4ff22a3818"
down_revision: Union[str, Sequence[str], None] = "a2fa02caf006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # 1) Add receipt_status_snapshot with default DRAFT (backfill existing rows)
    op.add_column(
        "inbound_receipt_lines",
        sa.Column(
            "receipt_status_snapshot",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'DRAFT'"),
        ),
    )

    # Remove server default after backfill to avoid hiding missing writes
    op.alter_column(
        "inbound_receipt_lines",
        "receipt_status_snapshot",
        existing_type=sa.String(length=32),
        server_default=None,
        existing_nullable=False,
    )

    # 2) Backfill snapshot from header status (idempotent)
    op.execute(
        """
UPDATE inbound_receipt_lines l
SET receipt_status_snapshot = r.status
FROM inbound_receipts r
WHERE r.id = l.receipt_id;
"""
    )

    # 3) Allow lot_id nullable (draft may be adjusted)
    op.alter_column(
        "inbound_receipt_lines",
        "lot_id",
        existing_type=sa.Integer(),
        nullable=True,
    )

    # 4) Lock enum + confirmed requires lot_id
    op.create_check_constraint(
        "ck_receipt_lines_status_snapshot_enum",
        "inbound_receipt_lines",
        sa.text("receipt_status_snapshot IN ('DRAFT','CONFIRMED')"),
    )

    op.create_check_constraint(
        "ck_receipt_lines_lot_required_on_confirmed",
        "inbound_receipt_lines",
        sa.text("(receipt_status_snapshot <> 'CONFIRMED') OR (lot_id IS NOT NULL)"),
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_constraint(
        "ck_receipt_lines_lot_required_on_confirmed",
        "inbound_receipt_lines",
        type_="check",
    )

    op.drop_constraint(
        "ck_receipt_lines_status_snapshot_enum",
        "inbound_receipt_lines",
        type_="check",
    )

    # revert lot_id to NOT NULL (best-effort; may fail if data contains NULLs)
    op.alter_column(
        "inbound_receipt_lines",
        "lot_id",
        existing_type=sa.Integer(),
        nullable=False,
    )

    op.drop_column("inbound_receipt_lines", "receipt_status_snapshot")
